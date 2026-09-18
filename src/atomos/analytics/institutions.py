"""
Atomos Institutional Analytics Engine

Computes:
1. Institutional Power Index (IPI: Composite 0-100 national school power rating)
2. Squad Depth, Break Conversion Rates & Debater Bench Strength
3. Head-to-Head School Rivalries & Direct Institutional Encounters
4. Comprehensive School Dossiers
"""

from collections import defaultdict
from dataclasses import dataclass, field
import sqlite3
from typing import Dict, List, Optional, Set, Tuple, Union

from atomos.analytics.ratings import EloRatingEngine
from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.master_tabs import MasterTabEngine


@dataclass
class TopDebater:
    person_id: int
    name: str
    master_score: Optional[float]
    national_rank: Optional[int]
    eligible_tournaments: int
    total_rounds: int


@dataclass
class TournamentCampaign:
    tournament_id: int
    tournament_name: str
    tournament_slug: str
    teams_entered: List[str]
    debates: int
    wins: int
    losses: int
    win_pct: float
    broke_to_knockouts: bool
    breaking_teams: List[str]


@dataclass
class InstitutionRivalryRecord:
    opponent_id: int
    opponent_name: str
    opponent_code: Optional[str]
    debates: int
    wins: int
    losses: int
    win_pct: float
    avg_margin: Optional[float]


@dataclass
class SchoolDirectMatchup:
    debate_id: int
    tournament_name: str
    tournament_slug: str
    round_number: int
    round_name: str
    round_type: str
    team_a_name: str
    team_b_name: str
    side_a: str
    side_b: str
    is_walkover: bool
    winner_school_name: str
    a_won: bool
    b_won: bool
    ballot_split: str
    margin_a: Optional[float]


@dataclass
class InstitutionProfile:
    institution_id: int
    name: str
    code: Optional[str]
    ipi_rank: Optional[int]
    ipi_score: Optional[float]
    tier: str  # 'National Powerhouse', 'Championship Contender', 'Competitive Program', 'Developing Program'
    squad_peak_elo: float
    squad_avg_elo: float
    
    # Career debate records
    total_debates: int
    wins: int
    losses: int
    win_rate: float
    
    # Proposition vs Opposition splits
    prop_debates: int
    prop_wins: int
    prop_win_pct: float
    opp_debates: int
    opp_wins: int
    opp_win_pct: float
    
    # Elimination records
    elim_debates: int
    elim_wins: int
    elim_losses: int
    elim_win_pct: float
    
    # Break metrics
    tournaments_entered: int
    tournaments_with_break: int
    total_breaks: int
    break_rate: float
    atss: Optional[float]
    
    # Squad depth
    teams_fielded: List[str]
    debater_count: int
    top_debaters: List[TopDebater]
    
    # Campaigns & Rivalries
    campaigns: List[TournamentCampaign]
    rivalries: List[InstitutionRivalryRecord]


@dataclass
class InstitutionHeadToHead:
    inst_a: InstitutionProfile
    inst_b: InstitutionProfile
    direct_debates: List[SchoolDirectMatchup]
    a_direct_wins: int
    b_direct_wins: int
    a_direct_margin_avg: Optional[float]
    b_direct_margin_avg: Optional[float]
    common_rivals: List[dict]


class InstitutionAnalytics:
    """Evaluates school performance and ranks debating institutions."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.critical_engine = CriticalStatsEngine(conn)

    def get_institutional_power_index(self, min_debates: int = 3, sort_by: str = "atiss") -> List[dict]:
        """
        Computes the national Institutional Power Index (IPI) out of 100.0.
        
        Weights:
        - Top Squad Strength (35%): Top teams Elo performance (Peak & Top-2 Avg)
        - National Win Rate (30%): Win rate across all debates (prelims & outrounds)
        - Elimination Success (20%): Outround wins and break conversion
        - Squad Depth (15%): Fielded debater pool and squad breadth
        """
        cur = self.conn.cursor()

        # 1. Fetch Elo ratings for all teams
        elo_engine = EloRatingEngine(self.conn)
        team_ratings = elo_engine.compute_team_ratings()

        # 2. Query all institutions
        cur.execute("SELECT id, name, code FROM institutions ORDER BY name")
        institutions = cur.fetchall()

        # 3. Query all teams per institution
        cur.execute("""
            SELECT t.id as team_id, t.name as team_name, t.institution_id,
                   inst.name as institution_name
            FROM teams t
            JOIN institutions inst ON t.institution_id = inst.id
        """)
        team_rows = cur.fetchall()

        inst_teams: Dict[int, List[str]] = {}
        for tr in team_rows:
            inst_teams.setdefault(tr["institution_id"], []).append(tr["team_name"])

        # 4. Query debater counts per institution
        cur.execute("""
            SELECT combined.institution_id, COUNT(DISTINCT combined.person_id) as debater_count
            FROM (
                SELECT t.institution_id, tm.person_id
                FROM teams t
                JOIN team_members tm ON t.id = tm.team_id
                UNION
                SELECT t.institution_id, sp.person_id
                FROM teams t
                JOIN speech_performances sp ON t.id = sp.team_id
            ) combined
            GROUP BY combined.institution_id
        """)
        debater_counts: Dict[int, int] = {r["institution_id"]: r["debater_count"] for r in cur.fetchall()}

        # 5. Query breaking teams from CriticalStatsEngine
        breaking_teams = self.critical_engine._get_breaking_teams()

        # 6. Query debate outcomes per institution with proper ballot aggregation
        cur.execute("""
            SELECT d.id as debate_id, r.round_type,
                   pt.institution_id as prop_inst_id,
                   ot.institution_id as opp_inst_id,
                   d.prop_team_id, d.opp_team_id,
                   d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
        """)
        debates = cur.fetchall()

        # 7. Query ATSS (Average Team Speaker Score) in prelims
        cur.execute("""
            SELECT t.institution_id,
                   AVG(CASE WHEN d.prop_team_id = t.id THEN deb_bal.prop_score ELSE deb_bal.opp_score END) as atss
            FROM teams t
            JOIN debates d ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
            JOIN rounds r ON d.round_id = r.id AND r.round_type = 'PRELIMINARY'
            JOIN (
                SELECT debate_id,
                       AVG(prop_total_score) as prop_score,
                       AVG(opp_total_score) as opp_score
                FROM adjudicator_ballots
                WHERE prop_total_score > 0 AND opp_total_score > 0
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE d.is_walkover = 0
            GROUP BY t.institution_id
        """)
        inst_atss: Dict[int, float] = {
            r["institution_id"]: round(float(r["atss"]), 5) for r in cur.fetchall() if r["atss"] is not None
        }

        inst_stats: Dict[int, dict] = {}
        for inst in institutions:
            inst_id = inst["id"]
            inst_stats[inst_id] = {
                "institution_id": inst_id,
                "name": inst["name"],
                "code": inst["code"],
                "total_debates": 0,
                "wins": 0,
                "elim_debates": 0,
                "elim_wins": 0,
            }

        for d in debates:
            p_inst = d["prop_inst_id"]
            o_inst = d["opp_inst_id"]
            is_elim = (d["round_type"] != "PRELIMINARY")
            is_wo = bool(d["is_walkover"])

            p_bal = d["prop_ballots"] or 0
            o_bal = d["opp_ballots"] or 0

            if is_wo:
                p_won = (d["walkover_winner_id"] == d["prop_team_id"])
                o_won = (d["walkover_winner_id"] == d["opp_team_id"])
            else:
                p_won = (p_bal > o_bal)
                o_won = (o_bal > p_bal)

            if p_inst and p_inst in inst_stats:
                st = inst_stats[p_inst]
                st["total_debates"] += 1
                if p_won:
                    st["wins"] += 1
                if is_elim:
                    st["elim_debates"] += 1
                    if p_won:
                        st["elim_wins"] += 1

            if o_inst and o_inst in inst_stats:
                st = inst_stats[o_inst]
                st["total_debates"] += 1
                if o_won:
                    st["wins"] += 1
                if is_elim:
                    st["elim_debates"] += 1
                    if o_won:
                        st["elim_wins"] += 1

        # 8. Query preliminary round team debate scores for ATISS computation
        cur.execute("""
            SELECT d.id as debate_id, r.tournament_id,
                   d.prop_team_id, d.opp_team_id,
                   pt.institution_id as prop_inst_id,
                   ot.institution_id as opp_inst_id,
                   AVG(CASE WHEN b.prop_total_score > 0 THEN b.prop_total_score END) as prop_score,
                   AVG(CASE WHEN b.opp_total_score > 0 THEN b.opp_total_score END) as opp_score
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
            GROUP BY d.id
        """)
        prelim_deb_rows = cur.fetchall()

        team_tourn_scores: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        inst_tourn_teams: Dict[Tuple[int, int], set] = defaultdict(set)

        for row in prelim_deb_rows:
            tid = row["tournament_id"]
            p_tid = row["prop_team_id"]
            o_tid = row["opp_team_id"]
            p_inst = row["prop_inst_id"]
            o_inst = row["opp_inst_id"]

            if p_inst and row["prop_score"] and row["prop_score"] > 0:
                team_tourn_scores[(p_tid, tid)].append(row["prop_score"])
                inst_tourn_teams[(p_inst, tid)].add(p_tid)

            if o_inst and row["opp_score"] and row["opp_score"] > 0:
                team_tourn_scores[(o_tid, tid)].append(row["opp_score"])
                inst_tourn_teams[(o_inst, tid)].add(o_tid)

        # For each institution and tournament:
        # Tournament ATISS = Combine Teams' ATSS / number of teams
        inst_tourn_atiss: Dict[Tuple[int, int], float] = {}
        inst_tournaments: Dict[int, set] = defaultdict(set)

        for (inst_id, tid), team_ids in inst_tourn_teams.items():
            team_atss_list = []
            for t_id in team_ids:
                scs = team_tourn_scores.get((t_id, tid), [])
                if scs:
                    team_atss_list.append(sum(scs) / len(scs))
            if team_atss_list:
                t_atiss = sum(team_atss_list) / len(team_atss_list)
                inst_tourn_atiss[(inst_id, tid)] = t_atiss
                inst_tournaments[inst_id].add(tid)

        # Final ATISS avg per institution: add those up and divide by number of tournaments
        inst_final_atiss: Dict[int, float] = {}
        for inst_id, t_ids in inst_tournaments.items():
            if t_ids:
                vals = [inst_tourn_atiss[(inst_id, tid)] for tid in t_ids]
                inst_final_atiss[inst_id] = sum(vals) / len(vals)

        # 9. Compute accurate highest break position using BracketEngine
        from atomos.analytics.brackets import BracketEngine
        bracket_engine = BracketEngine(self.conn)

        cur.execute("SELECT id, slug FROM tournaments ORDER BY id")
        all_tourns = cur.fetchall()

        # inst_name -> (rank_score, label)
        # 5: Champion, 4: Finalist, 3: Semifinalist, 2: Quarterfinalist, 1: Octofinalist
        inst_highest_break: Dict[str, tuple] = defaultdict(lambda: (0, "-"))

        for t in all_tourns:
            slug = t["slug"]
            b = bracket_engine.get_tournament_bracket(slug)
            if not b:
                continue
            stages = b.get("stages", [])
            for stage in stages:
                sname = stage["stage_name"]
                matchups = stage.get("matchups", [])
                for m in matchups:
                    p_inst = m["proposition"]["institution"]
                    o_inst = m["opposition"]["institution"]
                    res = m["result"]
                    w_side = res["winner_side"]
                    p_won = (w_side == "Proposition")
                    o_won = (w_side == "Opposition")

                    if sname == "Grand Final":
                        champ = p_inst if p_won else (o_inst if o_won else None)
                        runner_up = o_inst if p_won else (p_inst if o_won else None)
                        if champ and 5 > inst_highest_break[champ][0]:
                            inst_highest_break[champ] = (5, "Champion")
                        if runner_up and 4 > inst_highest_break[runner_up][0]:
                            inst_highest_break[runner_up] = (4, "Finalist")
                    elif sname == "Semifinals":
                        loser = o_inst if p_won else (p_inst if o_won else None)
                        if loser and 3 > inst_highest_break[loser][0]:
                            inst_highest_break[loser] = (3, "Semifinalist")
                    elif sname in ("Quarterfinals", "Quarters"):
                        loser = o_inst if p_won else (p_inst if o_won else None)
                        if loser and 2 > inst_highest_break[loser][0]:
                            inst_highest_break[loser] = (2, "Quarterfinalist")
                    elif "octo" in sname.lower():
                        loser = o_inst if p_won else (p_inst if o_won else None)
                        if loser and 1 > inst_highest_break[loser][0]:
                            inst_highest_break[loser] = (1, "Octofinalist")

        # 10. Query distinct tournaments debated per institution and breaking teams
        cur.execute("""
            SELECT institution_id, COUNT(DISTINCT tournament_id) as tournaments_debated
            FROM teams
            WHERE institution_id IS NOT NULL
            GROUP BY institution_id
        """)
        inst_tourn_map: Dict[int, int] = {r["institution_id"]: r["tournaments_debated"] for r in cur.fetchall()}

        cur.execute("SELECT name, institution_id, tournament_id FROM teams WHERE institution_id IS NOT NULL")
        inst_tourn_breaks: Dict[int, set] = defaultdict(set)
        for tr in cur.fetchall():
            if (tr["name"], tr["tournament_id"]) in breaking_teams:
                inst_tourn_breaks[tr["institution_id"]].add(tr["tournament_id"])

        # 11. Calculate composite scores & enriched school metrics
        results = []
        for inst_id, st in inst_stats.items():
            teams = inst_teams.get(inst_id, [])
            team_count = len(teams)
            if team_count == 0 or st["total_debates"] < min_debates:
                continue

            # Squad Elo: Peak and average of top 2 teams
            team_elos = [team_ratings[t]["rating"] for t in teams if t in team_ratings]
            team_elos.sort(reverse=True)
            peak_elo = team_elos[0] if team_elos else 1500.0
            top_elos = team_elos[:2] if len(team_elos) >= 2 else team_elos
            squad_elo = sum(top_elos) / len(top_elos) if top_elos else 1500.0

            # Win Rate (0 - 100%)
            win_rate = (st["wins"] / st["total_debates"] * 100.0) if st["total_debates"] > 0 else 0.0

            # Out-round conversion
            elim_success = (st["elim_wins"] * 8.0) + (st["elim_debates"] * 4.0)

            # Depth: debater count & teams
            num_debaters = debater_counts.get(inst_id, team_count * 3)
            depth_metric = min(100.0, (num_debaters * 3.5) + (team_count * 2.0))

            # Normalized Elo score (1350 - 1950 mapped smoothly to 0 - 100)
            elo_normalized = max(0.0, min(100.0, (squad_elo - 1350.0) / 6.0))

            # Composite IPI (0 - 100)
            ipi = round(
                (elo_normalized * 0.35) +
                (win_rate * 0.30) +
                (min(100.0, elim_success) * 0.20) +
                (depth_metric * 0.15),
                5
            )

            # Breaks & Tournament stats
            breaks = sum(1 for (tname, tid) in breaking_teams if tname in teams)
            t_debated = len(inst_tournaments.get(inst_id, set())) or inst_tourn_map.get(inst_id, 0)
            t_breaks = len(inst_tourn_breaks.get(inst_id, set()))
            break_percentage = round((t_breaks / t_debated * 100.0), 1) if t_debated > 0 else 0.0
            highest_pos = inst_highest_break.get(st["name"], (0, "-"))[1]
            final_atiss_val = round(inst_final_atiss[inst_id], 2) if inst_id in inst_final_atiss else (round(inst_atss[inst_id], 2) if inst_id in inst_atss else None)

            results.append({
                "institution_id": inst_id,
                "name": st["name"],
                "code": st["code"],
                "ipi": ipi,
                "atiss": final_atiss_val,
                "squad_peak_elo": round(peak_elo, 5),
                "squad_avg_elo": round(squad_elo, 5),
                "teams_fielded": team_count,
                "debater_count": num_debaters,
                "total_debates": st["total_debates"],
                "wins": st["wins"],
                "win_rate": round(win_rate, 5),
                "elim_debates": st["elim_debates"],
                "elim_wins": st["elim_wins"],
                "breaks_count": breaks,
                "tournaments_debated": t_debated,
                "break_percentage": break_percentage,
                "highest_break": highest_pos,
            })

        # Rank schools primarily by ATISS (Average Total Institutional Speaker Score), secondary by win_rate, tertiary by IPI
        # Rank schools according to requested sort_by ('atiss' or 'ipi')
        if sort_by == "ipi":
            results.sort(
                key=lambda x: (
                    x["ipi"],
                    x["atiss"] if x["atiss"] is not None else 0.0,
                    x["win_rate"],
                ),
                reverse=True,
            )
        else:
            results.sort(
                key=lambda x: (
                    x["atiss"] if x["atiss"] is not None else 0.0,
                    x["win_rate"],
                    x["ipi"],
                ),
                reverse=True,
            )
        for rank, r in enumerate(results, start=1):
            r["rank"] = rank

        return results

    def get_institutional_delta_leaderboard(self) -> List[dict]:
        """
        Computes the official Institutional Delta Leaderboard.
        
        Rules:
        - Rank schools strictly by Institutional Delta.
        - Formula:
            Delta = (A_ATSS + (1/2 * B_ATSS) + (1/3 * C_ATSS) + ...) / divider
            divider = 1 + 1/2 + 1/3 + ...
            (1 team = 1.0, 2 teams = 1.5, 3 teams = 1.8333, etc.)
        - Columns:
            - rank: 1..N
            - institution_name: Name of school
            - name: Name of school
            - code: Institutional code (if any)
            - delta: float rounded to 2 decimals
            - a_atss: Team A ATSS (float or None)
            - b_atss: Team B ATSS (float or None)
            - net_diff: Team A ATSS - Team B ATSS (float or None)
            - tournaments_existed: Total distinct tournaments where the school entered >= 1 team
            - break_percentage: (Break % Team A + Break % Team B) / 2.0 (or Team A Break % if no B team)
            - highest_break: Highest position achieved by any team of that school
        """
        cur = self.conn.cursor()

        # Query institution codes
        cur.execute("SELECT id, name, code FROM institutions")
        inst_codes = {r["name"]: r["code"] for r in cur.fetchall()}

        # 1. Fetch team stats across all tournaments (min_tournaments=1)
        all_teams = self.critical_engine.get_critical_team_stats(min_tournaments=1)

        # 2. Group teams by institution
        inst_teams = defaultdict(list)
        for t in all_teams:
            inst_name = t.get("institution")
            if inst_name and inst_name != "Independent":
                inst_teams[inst_name].append(t)

        # 3. For each institution, query tournaments existed
        cur.execute("""
            SELECT i.name as institution_name, COUNT(DISTINCT r.tournament_id) as tours_existed
            FROM teams tm
            JOIN institutions i ON tm.institution_id = i.id
            JOIN debates d ON (tm.id = d.prop_team_id OR tm.id = d.opp_team_id)
            JOIN rounds r ON d.round_id = r.id
            GROUP BY i.name
        """)
        tours_existed_map = {r["institution_name"]: r["tours_existed"] for r in cur.fetchall()}

        ach_order = ["Champion", "Finalist", "Semifinalist", "Quarterfinalist", "Octofinalist", "Novice Champion", "Novice Finalist", "Novice Semifinalist", "-"]
        def ach_rank(t):
            ach = t.get("highest_achievement", "-")
            try:
                return ach_order.index(ach)
            except ValueError:
                return 99

        inst_leaderboard = []
        for inst, t_list in inst_teams.items():
            # Sort teams: A, B, C...
            def team_tier_key(t):
                name = t["team_name"].upper().strip()
                if name.endswith(" A"): return (1, -t.get("atss", 0))
                if name.endswith(" B"): return (2, -t.get("atss", 0))
                if name.endswith(" C"): return (3, -t.get("atss", 0))
                if name.endswith(" D"): return (4, -t.get("atss", 0))
                if name.endswith(" E"): return (5, -t.get("atss", 0))
                return (10, -t.get("atss", 0))

            sorted_teams = sorted(t_list, key=team_tier_key)
            a_team = next((t for t in sorted_teams if t["team_name"].upper().strip().endswith(" A")), None)
            b_team = next((t for t in sorted_teams if t["team_name"].upper().strip().endswith(" B")), None)

            if not a_team and sorted_teams:
                a_team = sorted_teams[0]
            if not b_team and len(sorted_teams) > 1 and sorted_teams[1] != a_team:
                b_team = sorted_teams[1]

            a_atss = round(float(a_team["atss"]), 2) if a_team and a_team.get("atss") else None
            b_atss = round(float(b_team["atss"]), 2) if b_team and b_team.get("atss") else None
            net_diff = round(a_atss - b_atss, 2) if (a_atss is not None and b_atss is not None) else None

            # Calculate Delta: (A + 1/2 B + 1/3 C + ...) / (1 + 1/2 + 1/3 + ...)
            weights = [1.0 / (k + 1) for k in range(len(sorted_teams))]
            weighted_sum = sum(float(t["atss"]) * w for t, w in zip(sorted_teams, weights))
            div_sum = sum(weights)
            delta = round(weighted_sum / div_sum, 2) if div_sum > 0 else 0.0

            # Number of tournaments existed
            tours_existed = tours_existed_map.get(inst, 0)
            if tours_existed == 0:
                tours_existed = max((t.get("tournaments_debated", 0) for t in sorted_teams), default=0)

            # Combined Break percentage: (Break % Team A + Break % Team B) / 2.0
            if a_team and b_team:
                break_pct = round((float(a_team["break_percentage"]) + float(b_team["break_percentage"])) / 2.0, 1)
            elif a_team:
                break_pct = round(float(a_team["break_percentage"]), 1)
            elif sorted_teams:
                break_pct = round(float(sorted_teams[0]["break_percentage"]), 1)
            else:
                break_pct = 0.0

            # Highest achievement across all teams
            best_team = min(sorted_teams, key=ach_rank) if sorted_teams else {}
            highest_ach = best_team.get("highest_achievement", "-")

            inst_leaderboard.append({
                "institution_name": inst,
                "name": inst,
                "code": inst_codes.get(inst),
                "delta": delta,
                "a_atss": a_atss,
                "b_atss": b_atss,
                "net_diff": net_diff,
                "tournaments_existed": tours_existed,
                "break_percentage": break_pct,
                "highest_break": highest_ach,
                "highest_achievement": highest_ach,
                # For backwards compatibility:
                "atiss": delta,
                "tournaments_debated": tours_existed,
                "win_rate": round(sum(t.get("win_percentage", 0) for t in sorted_teams) / len(sorted_teams), 1) if sorted_teams else 0.0,
            })

        # Rank schools strictly by Delta descending, secondary by tournaments_existed descending
        inst_leaderboard.sort(key=lambda x: (x["delta"], x["tournaments_existed"]), reverse=True)
        for idx, row in enumerate(inst_leaderboard, start=1):
            row["rank"] = idx

        return inst_leaderboard


    def get_institution_profile(self, identifier: Union[int, str]) -> Optional[InstitutionProfile]:
        """Fetch comprehensive dossier for an institution."""
        cur = self.conn.cursor()

        # Resolve institution
        inst_row = None
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            cur.execute("SELECT id, name, code FROM institutions WHERE id = ?", (int(identifier),))
            inst_row = cur.fetchone()
        elif isinstance(identifier, str):
            # Exact match
            cur.execute("SELECT id, name, code FROM institutions WHERE LOWER(name) = LOWER(?)", (identifier.strip(),))
            inst_row = cur.fetchone()
            if not inst_row:
                # Code match
                cur.execute("SELECT id, name, code FROM institutions WHERE LOWER(code) = LOWER(?)", (identifier.strip(),))
                inst_row = cur.fetchone()
            if not inst_row:
                # Substring match
                cur.execute("SELECT id, name, code FROM institutions WHERE name LIKE ? ORDER BY LENGTH(name) LIMIT 1", (f"%{identifier.strip()}%",))
                inst_row = cur.fetchone()

        if not inst_row:
            return None

        inst_id = inst_row["id"]
        inst_name = inst_row["name"]
        inst_code = inst_row["code"]

        # 1. Fetch IPI standing
        all_ipi = self.get_institutional_power_index(min_debates=1)
        ipi_data = next((r for r in all_ipi if r["institution_id"] == inst_id), None)
        
        ipi_rank = ipi_data["rank"] if ipi_data else None
        ipi_score = ipi_data["ipi"] if ipi_data else None
        peak_elo = ipi_data["squad_peak_elo"] if ipi_data else 1500.0
        avg_elo = ipi_data["squad_avg_elo"] if ipi_data else 1500.0

        if ipi_score is not None:
            if ipi_score >= 88.0:
                tier = "National Powerhouse"
            elif ipi_score >= 75.0:
                tier = "Championship Contender"
            elif ipi_score >= 50.0:
                tier = "Competitive Program"
            else:
                tier = "Developing Program"
        else:
            tier = "Unranked"

        # 2. Query debate records with Prop/Opp and Prelim/Elim splits
        cur.execute("""
            SELECT d.id as debate_id, r.round_type,
                   CASE WHEN d.prop_team_id = t.id THEN 'Proposition' ELSE 'Opposition' END as team_side,
                   d.is_walkover, d.walkover_winner_id, t.id as my_team_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots
            FROM teams t
            JOIN debates d ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
            JOIN rounds r ON d.round_id = r.id
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE t.institution_id = ?
        """, (inst_id,))
        deb_rows = cur.fetchall()

        total_debates = len(deb_rows)
        wins = 0
        prop_deb = 0
        prop_w = 0
        opp_deb = 0
        opp_w = 0
        elim_deb = 0
        elim_w = 0

        for r in deb_rows:
            side = r["team_side"]
            is_elim = (r["round_type"] != "PRELIMINARY")
            p_b = r["prop_ballots"] or 0
            o_b = r["opp_ballots"] or 0

            if r["is_walkover"]:
                won = (r["walkover_winner_id"] == r["my_team_id"])
            else:
                won = (side == "Proposition" and p_b > o_b) or (side == "Opposition" and o_b > p_b)

            if won:
                wins += 1

            if side == "Proposition":
                prop_deb += 1
                if won:
                    prop_w += 1
            else:
                opp_deb += 1
                if won:
                    opp_w += 1

            if is_elim:
                elim_deb += 1
                if won:
                    elim_w += 1

        win_rate = round(wins / total_debates * 100.0, 5) if total_debates > 0 else 0.0
        prop_win_pct = round(prop_w / prop_deb * 100.0, 5) if prop_deb > 0 else 0.0
        opp_win_pct = round(opp_w / opp_deb * 100.0, 5) if opp_deb > 0 else 0.0
        elim_win_pct = round(elim_w / elim_deb * 100.0, 5) if elim_deb > 0 else 0.0

        # 3. Teams and debaters fielded
        cur.execute("SELECT DISTINCT name FROM teams WHERE institution_id = ? ORDER BY name", (inst_id,))
        teams_fielded = [r[0] for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(DISTINCT person_id) as debater_count
            FROM (
                SELECT tm.person_id FROM teams t JOIN team_members tm ON t.id = tm.team_id WHERE t.institution_id = ?
                UNION
                SELECT sp.person_id FROM teams t JOIN speech_performances sp ON t.id = sp.team_id WHERE t.institution_id = ?
            )
        """, (inst_id, inst_id))
        debater_count = cur.fetchone()["debater_count"] or len(teams_fielded) * 3

        # 4. Top Debaters from Master Speaker Tab
        mte = MasterTabEngine(self.conn)
        master_speakers = mte.get_master_speaker_tab()
        top_debaters: List[TopDebater] = []
        for s in master_speakers:
            if s.get("institution_name") == inst_name:
                top_debaters.append(
                    TopDebater(
                        person_id=s["person_id"],
                        name=s["speaker_name"],
                        master_score=round(s["master_score"], 5) if s["master_score"] else None,
                        national_rank=s["rank"],
                        eligible_tournaments=s["eligible_tournaments"],
                        total_rounds=s["total_rounds"],
                    )
                )

        # 5. Tournament campaigns & breaks
        breaking_teams_set = self.critical_engine._get_breaking_teams()
        cur.execute("""
            SELECT DISTINCT t.tournament_id, tour.name as tour_name, tour.slug as tour_slug
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            WHERE t.institution_id = ?
            ORDER BY tour.id
        """, (inst_id,))
        tours = cur.fetchall()

        campaigns: List[TournamentCampaign] = []
        tournaments_with_break = 0
        total_breaks = 0

        for t_info in tours:
            tid = t_info["tournament_id"]
            tname = t_info["tour_name"]
            tslug = t_info["tour_slug"]

            # Teams entered
            cur.execute("SELECT id, name FROM teams WHERE tournament_id = ? AND institution_id = ?", (tid, inst_id))
            entered_rows = cur.fetchall()
            entered_names = [r["name"] for r in entered_rows]
            entered_ids = {r["id"] for r in entered_rows}

            # Campaign record
            c_debates = 0
            c_wins = 0
            for r in deb_rows:
                if r["my_team_id"] in entered_ids:
                    c_debates += 1
                    side = r["team_side"]
                    p_b = r["prop_ballots"] or 0
                    o_b = r["opp_ballots"] or 0
                    if r["is_walkover"]:
                        if r["walkover_winner_id"] == r["my_team_id"]:
                            c_wins += 1
                    elif (side == "Proposition" and p_b > o_b) or (side == "Opposition" and o_b > p_b):
                        c_wins += 1

            c_win_pct = round(c_wins / c_debates * 100.0, 5) if c_debates > 0 else 0.0
            
            # Breaks in this tournament
            brk_teams = [name for name in entered_names if (name, tid) in breaking_teams_set]
            has_break = len(brk_teams) > 0
            if has_break:
                tournaments_with_break += 1
                total_breaks += len(brk_teams)

            campaigns.append(
                TournamentCampaign(
                    tournament_id=tid,
                    tournament_name=tname,
                    tournament_slug=tslug,
                    teams_entered=entered_names,
                    debates=c_debates,
                    wins=c_wins,
                    losses=c_debates - c_wins,
                    win_pct=c_win_pct,
                    broke_to_knockouts=has_break,
                    breaking_teams=brk_teams,
                )
            )

        break_rate = round(tournaments_with_break / len(tours) * 100.0, 5) if tours else 0.0
        atss = ipi_data.get("atss") if ipi_data else None

        # 6. School Rivalries
        rivalries = self.get_institution_rivalries(inst_id)

        return InstitutionProfile(
            institution_id=inst_id,
            name=inst_name,
            code=inst_code,
            ipi_rank=ipi_rank,
            ipi_score=ipi_score,
            tier=tier,
            squad_peak_elo=peak_elo,
            squad_avg_elo=avg_elo,
            total_debates=total_debates,
            wins=wins,
            losses=total_debates - wins,
            win_rate=win_rate,
            prop_debates=prop_deb,
            prop_wins=prop_w,
            prop_win_pct=prop_win_pct,
            opp_debates=opp_deb,
            opp_wins=opp_w,
            opp_win_pct=opp_win_pct,
            elim_debates=elim_deb,
            elim_wins=elim_w,
            elim_losses=elim_deb - elim_w,
            elim_win_pct=elim_win_pct,
            tournaments_entered=len(tours),
            tournaments_with_break=tournaments_with_break,
            total_breaks=total_breaks,
            break_rate=break_rate,
            atss=atss,
            teams_fielded=teams_fielded,
            debater_count=debater_count,
            top_debaters=top_debaters,
            campaigns=campaigns,
            rivalries=rivalries,
        )

    def get_institution_rivalries(self, inst_id: int) -> List[InstitutionRivalryRecord]:
        """Compute head-to-head match records against all other institutions."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT opp_inst.id as opp_id, opp_inst.name as opp_name, opp_inst.code as opp_code,
                   COUNT(DISTINCT d.id) as debates,
                   SUM(CASE 
                       WHEN d.is_walkover = 1 AND d.walkover_winner_id = my_t.id THEN 1
                       WHEN (d.prop_team_id = my_t.id AND deb_bal.prop_ballots > deb_bal.opp_ballots)
                         OR (d.opp_team_id = my_t.id AND deb_bal.opp_ballots > deb_bal.prop_ballots) THEN 1
                       ELSE 0 END) as wins,
                   AVG(CASE WHEN d.prop_team_id = my_t.id THEN deb_bal.prop_margin ELSE -deb_bal.prop_margin END) as avg_margin
            FROM teams my_t
            JOIN debates d ON (my_t.id = d.prop_team_id OR my_t.id = d.opp_team_id)
            JOIN teams opp_t ON ((d.prop_team_id = my_t.id AND d.opp_team_id = opp_t.id)
                              OR (d.opp_team_id = my_t.id AND d.prop_team_id = opp_t.id))
            JOIN institutions opp_inst ON opp_t.institution_id = opp_inst.id
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                       AVG(prop_total_score - opp_total_score) as prop_margin
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE my_t.institution_id = ? AND opp_inst.id != ?
            GROUP BY opp_inst.id
            ORDER BY debates DESC, wins DESC
        """, (inst_id, inst_id))

        records: List[InstitutionRivalryRecord] = []
        for r in cur.fetchall():
            cnt = r["debates"]
            w = r["wins"] or 0
            pct = round(w / cnt * 100.0, 5) if cnt > 0 else 0.0
            margin = round(float(r["avg_margin"]), 5) if r["avg_margin"] is not None else None
            records.append(
                InstitutionRivalryRecord(
                    opponent_id=r["opp_id"],
                    opponent_name=r["opp_name"],
                    opponent_code=r["opp_code"],
                    debates=cnt,
                    wins=w,
                    losses=cnt - w,
                    win_pct=pct,
                    avg_margin=margin,
                )
            )
        return records

    def compare_institutions(self, id_a: int, id_b: int) -> Optional[InstitutionHeadToHead]:
        """Generate side-by-side head-to-head comparison between two institutions."""
        prof_a = self.get_institution_profile(id_a)
        prof_b = self.get_institution_profile(id_b)

        if not prof_a or not prof_b:
            return None

        cur = self.conn.cursor()

        # Query all direct debates between any teams of School A and School B
        cur.execute("""
            SELECT d.id as debate_id, tour.name as tour_name, tour.slug as tour_slug,
                   r.round_number, r.name as round_name, r.round_type,
                   t1.name as prop_team_name, t2.name as opp_team_name,
                   t1.institution_id as prop_inst_id, t2.institution_id as opp_inst_id,
                   d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots, deb_bal.prop_margin
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t1 ON d.prop_team_id = t1.id
            JOIN teams t2 ON d.opp_team_id = t2.id
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                       AVG(prop_total_score - opp_total_score) as prop_margin
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE (t1.institution_id = ? AND t2.institution_id = ?)
               OR (t1.institution_id = ? AND t2.institution_id = ?)
            ORDER BY tour.id, r.round_number
        """, (id_a, id_b, id_b, id_a))
        rows = cur.fetchall()

        direct_matches: List[SchoolDirectMatchup] = []
        a_direct_wins = 0
        b_direct_wins = 0
        margins_a: List[float] = []

        for r in rows:
            a_is_prop = (r["prop_inst_id"] == id_a)
            side_a = "Proposition" if a_is_prop else "Opposition"
            side_b = "Opposition" if a_is_prop else "Proposition"
            team_a = r["prop_team_name"] if a_is_prop else r["opp_team_name"]
            team_b = r["opp_team_name"] if a_is_prop else r["prop_team_name"]

            p_bal = r["prop_ballots"] or 0
            o_bal = r["opp_ballots"] or 0
            is_wo = bool(r["is_walkover"])

            if is_wo:
                winner_inst = r["prop_inst_id"] if r["walkover_winner_id"] == r["prop_team_id"] else r["opp_inst_id"]
                a_won = (winner_inst == id_a)
                b_won = not a_won
                split_str = "WALKOVER"
                margin_a = None
            else:
                if a_is_prop:
                    a_won = p_bal > o_bal
                    b_won = o_bal > p_bal
                    margin_a = round(r["prop_margin"], 5) if r["prop_margin"] is not None else None
                else:
                    a_won = o_bal > p_bal
                    b_won = p_bal > o_bal
                    margin_a = round(-r["prop_margin"], 5) if r["prop_margin"] is not None else None
                split_str = f"{max(p_bal, o_bal)}-{min(p_bal, o_bal)}"

            if a_won:
                a_direct_wins += 1
                winner_school = prof_a.name
            elif b_won:
                b_direct_wins += 1
                winner_school = prof_b.name
            else:
                winner_school = "Draw"

            if margin_a is not None:
                margins_a.append(margin_a)

            direct_matches.append(
                SchoolDirectMatchup(
                    debate_id=r["debate_id"],
                    tournament_name=r["tour_name"],
                    tournament_slug=r["tour_slug"],
                    round_number=r["round_number"],
                    round_name=r["round_name"],
                    round_type=r["round_type"],
                    team_a_name=team_a,
                    team_b_name=team_b,
                    side_a=side_a,
                    side_b=side_b,
                    is_walkover=is_wo,
                    winner_school_name=winner_school,
                    a_won=a_won,
                    b_won=b_won,
                    ballot_split=split_str,
                    margin_a=margin_a,
                )
            )

        a_avg_margin = round(sum(margins_a) / len(margins_a), 5) if margins_a else None
        b_avg_margin = round(-a_avg_margin, 5) if a_avg_margin is not None else None

        # Common rival schools
        rivals_a = {r.opponent_id: r for r in prof_a.rivalries}
        rivals_b = {r.opponent_id: r for r in prof_b.rivalries}
        common_ids = set(rivals_a.keys()).intersection(set(rivals_b.keys()))

        common_list = []
        for oid in common_ids:
            ra = rivals_a[oid]
            rb = rivals_b[oid]
            common_list.append({
                "opponent_id": oid,
                "opponent_name": ra.opponent_name,
                "opponent_code": ra.opponent_code,
                "a_debates": ra.debates,
                "a_wins": ra.wins,
                "a_win_pct": ra.win_pct,
                "a_avg_margin": ra.avg_margin,
                "b_debates": rb.debates,
                "b_wins": rb.wins,
                "b_win_pct": rb.win_pct,
                "b_avg_margin": rb.avg_margin,
            })
        common_list.sort(key=lambda x: (x["a_debates"] + x["b_debates"]), reverse=True)

        return InstitutionHeadToHead(
            inst_a=prof_a,
            inst_b=prof_b,
            direct_debates=direct_matches,
            a_direct_wins=a_direct_wins,
            b_direct_wins=b_direct_wins,
            a_direct_margin_avg=a_avg_margin,
            b_direct_margin_avg=b_avg_margin,
            common_rivals=common_list,
        )
