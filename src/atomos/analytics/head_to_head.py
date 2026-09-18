"""
Atomos Head-to-Head Debater & Team Comparison Engine

Extracts direct matchup history, common opponent records, speaker score differentials,
and side-by-side critical performance metrics between any two debaters or teams.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
import sqlite3
from typing import Dict, List, Optional, Set, Tuple

from atomos.analytics.debater_profile import DebaterProfile, DebaterProfileEngine
from atomos.analytics.tournaments import CLEAN_TOURNAMENT_NAMES


@dataclass
class DirectDebateMatchup:
    debate_id: int
    tournament_name: str
    tournament_slug: str
    round_number: int
    round_name: str
    round_type: str  # 'PRELIMINARY', 'ELIMINATION'
    
    # Team identities
    team_a_name: str
    team_b_name: str
    side_a: str  # 'Proposition', 'Opposition'
    side_b: str
    
    # Debate outcome
    is_walkover: bool
    winner_team_name: Optional[str]
    a_won: bool
    b_won: bool
    ballot_split: str  # e.g. '3-0', '2-1', '1-0'
    margin_a: Optional[float]  # positive if A won, negative if B won
    
    # Debater specific scores (when comparing debaters)
    sub_score_a: Optional[float] = None
    pos_a: Optional[str] = None
    rep_score_a: Optional[float] = None
    sub_score_b: Optional[float] = None
    pos_b: Optional[str] = None
    rep_score_b: Optional[float] = None


@dataclass
class CommonOpponentRecord:
    opponent_name: str
    opponent_institution: Optional[str]
    a_debates: int
    a_wins: int
    a_win_pct: float
    a_avg_margin: Optional[float]
    b_debates: int
    b_wins: int
    b_win_pct: float
    b_avg_margin: Optional[float]


@dataclass
class DebaterHeadToHead:
    debater_a: DebaterProfile
    debater_b: DebaterProfile
    
    # Direct encounters
    direct_debates: List[DirectDebateMatchup]
    a_direct_wins: int
    b_direct_wins: int
    a_direct_sub_avg: Optional[float]
    b_direct_sub_avg: Optional[float]
    
    # Mutual rivals
    common_opponents: List[CommonOpponentRecord]

    # Tour-to-tour consistency standard deviation
    a_consistency_std_dev: Optional[float] = None
    b_consistency_std_dev: Optional[float] = None


@dataclass
class TeamHeadToHead:
    team_a_name: str
    team_b_name: str
    institution_a: str
    institution_b: str
    
    # Direct encounters
    direct_debates: List[DirectDebateMatchup]
    a_direct_wins: int
    b_direct_wins: int
    a_direct_margin_avg: Optional[float]
    b_direct_margin_avg: Optional[float]
    
    # Career summaries
    metrics_a: dict
    metrics_b: dict
    
    # Mutual rivals
    common_opponents: List[CommonOpponentRecord]


class HeadToHeadEngine:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.profile_engine = DebaterProfileEngine(conn)

    def compare_debaters(self, person_id_a: int, person_id_b: int) -> Optional[DebaterHeadToHead]:
        """Generate comprehensive head-to-head comparison between two debaters."""
        prof_a = self.profile_engine.get_profile(person_id_a)
        prof_b = self.profile_engine.get_profile(person_id_b)
        
        if not prof_a or not prof_b:
            return None

        cur = self.conn.cursor()

        # 1. Find all debates where both debaters spoke on opposing sides
        cur.execute(
            """
            SELECT DISTINCT d.id as debate_id, t.id as tour_id, t.name as tour_name, t.slug as tour_slug,
                   r.round_number, r.name as round_name, r.round_type,
                   t1.name as prop_team_name, t2.name as opp_team_name,
                   d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots, deb_bal.prop_margin
            FROM speech_performances sp_a
            JOIN speech_performances sp_b ON sp_a.debate_id = sp_b.debate_id AND sp_a.side != sp_b.side
            JOIN debates d ON sp_a.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
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
            WHERE sp_a.person_id = ? AND sp_b.person_id = ?
            ORDER BY t.id, r.round_number
            """,
            (person_id_a, person_id_b),
        )
        debate_rows = cur.fetchall()

        direct_matches: List[DirectDebateMatchup] = []
        a_direct_wins = 0
        b_direct_wins = 0
        a_direct_sub_scores: List[float] = []
        b_direct_sub_scores: List[float] = []

        for row in debate_rows:
            d_id = row["debate_id"]
            
            # Fetch A's speeches in this debate
            cur.execute(
                """
                SELECT position, speech_type, AVG(total_score) as avg_score, side, team_id
                FROM speech_performances
                WHERE debate_id = ? AND person_id = ?
                GROUP BY position, speech_type
                ORDER BY CASE WHEN speech_type = 'SUBSTANTIVE' THEN 1 ELSE 2 END
                """,
                (d_id, person_id_a),
            )
            a_sp_rows = cur.fetchall()
            
            # Fetch B's speeches in this debate
            cur.execute(
                """
                SELECT position, speech_type, AVG(total_score) as avg_score, side, team_id
                FROM speech_performances
                WHERE debate_id = ? AND person_id = ?
                GROUP BY position, speech_type
                ORDER BY CASE WHEN speech_type = 'SUBSTANTIVE' THEN 1 ELSE 2 END
                """,
                (d_id, person_id_b),
            )
            b_sp_rows = cur.fetchall()

            side_a = a_sp_rows[0]["side"] if a_sp_rows else "Unknown"
            side_b = b_sp_rows[0]["side"] if b_sp_rows else "Unknown"
            
            team_a_name = row["prop_team_name"] if side_a == "Proposition" else row["opp_team_name"]
            team_b_name = row["opp_team_name"] if side_a == "Proposition" else row["prop_team_name"]

            # Substantive & reply scores
            a_sub = next((r for r in a_sp_rows if r["speech_type"] == "SUBSTANTIVE"), None)
            a_rep = next((r for r in a_sp_rows if r["speech_type"] == "REPLY"), None)
            b_sub = next((r for r in b_sp_rows if r["speech_type"] == "SUBSTANTIVE"), None)
            b_rep = next((r for r in b_sp_rows if r["speech_type"] == "REPLY"), None)

            sub_score_a = round(float(a_sub["avg_score"]), 5) if a_sub else None
            sub_score_b = round(float(b_sub["avg_score"]), 5) if b_sub else None
            rep_score_a = round(float(a_rep["avg_score"]), 5) if a_rep else None
            rep_score_b = round(float(b_rep["avg_score"]), 5) if b_rep else None

            if sub_score_a is not None:
                a_direct_sub_scores.append(sub_score_a)
            if sub_score_b is not None:
                b_direct_sub_scores.append(sub_score_b)

            # Determine winner
            p_bal = row["prop_ballots"] or 0
            o_bal = row["opp_ballots"] or 0
            is_wo = bool(row["is_walkover"])
            
            if is_wo:
                a_won = (row["walkover_winner_id"] == a_sp_rows[0]["team_id"]) if a_sp_rows else False
                b_won = not a_won
                split_str = "WALKOVER"
                margin_a = None
            else:
                if side_a == "Proposition":
                    a_won = p_bal > o_bal
                    b_won = o_bal > p_bal
                    margin_a = round(row["prop_margin"], 5) if row["prop_margin"] is not None else None
                else:
                    a_won = o_bal > p_bal
                    b_won = p_bal > o_bal
                    margin_a = round(-row["prop_margin"], 5) if row["prop_margin"] is not None else None
                split_str = f"{max(p_bal, o_bal)}-{min(p_bal, o_bal)}"

            if a_won:
                a_direct_wins += 1
                winner_team = team_a_name
            elif b_won:
                b_direct_wins += 1
                winner_team = team_b_name
            else:
                winner_team = "Draw / Unrecorded"

            # Clean tournament and round names
            tour_id = row["tour_id"] if "tour_id" in row.keys() else None
            clean_tname = CLEAN_TOURNAMENT_NAMES.get(tour_id, row["tour_name"]) if tour_id else row["tour_name"]

            raw_rname = row["round_name"] or f"Round {row['round_number']}"
            clean_rname = raw_rname
            if "Welcome to" in clean_rname:
                for stage in ["Grand Final", "Grand Finals", "Semifinals", "Quarterfinals", "Octofinals", "Partial Octos"]:
                    if stage.lower() in clean_rname.lower():
                        clean_rname = stage
                        break
                else:
                    if "round" in clean_rname.lower():
                        clean_rname = f"Round {row['round_number']}"

            direct_matches.append(
                DirectDebateMatchup(
                    debate_id=d_id,
                    tournament_name=clean_tname,
                    tournament_slug=row["tour_slug"],
                    round_number=row["round_number"],
                    round_name=clean_rname,
                    round_type=row["round_type"],
                    team_a_name=team_a_name,
                    team_b_name=team_b_name,
                    side_a=side_a,
                    side_b=side_b,
                    is_walkover=is_wo,
                    winner_team_name=winner_team,
                    a_won=a_won,
                    b_won=b_won,
                    ballot_split=split_str,
                    margin_a=margin_a,
                    sub_score_a=sub_score_a,
                    pos_a=a_sub["position"] if a_sub else None,
                    rep_score_a=rep_score_a,
                    sub_score_b=sub_score_b,
                    pos_b=b_sub["position"] if b_sub else None,
                    rep_score_b=rep_score_b,
                )
            )

        # 2. Common Opponents Analysis
        common_opponents = self._calculate_common_opponents_debater(person_id_a, person_id_b)

        a_direct_avg = round(sum(a_direct_sub_scores) / len(a_direct_sub_scores), 5) if a_direct_sub_scores else None
        b_direct_avg = round(sum(b_direct_sub_scores) / len(b_direct_sub_scores), 5) if b_direct_sub_scores else None

        # 3. Tournament-to-Tournament Consistency (Standard Deviation of Tournament Averages)
        def _calc_consistency(prof: DebaterProfile) -> Optional[float]:
            if not prof or not prof.tournaments:
                return None
            avgs = [t.tournament_average for t in prof.tournaments if t.tournament_average is not None and t.tournament_average > 0]
            if len(avgs) < 2:
                return None
            mean = sum(avgs) / len(avgs)
            var = sum((x - mean) ** 2 for x in avgs) / len(avgs)
            return round(math.sqrt(var), 2)

        a_consistency = _calc_consistency(prof_a)
        b_consistency = _calc_consistency(prof_b)

        return DebaterHeadToHead(
            debater_a=prof_a,
            debater_b=prof_b,
            direct_debates=direct_matches,
            a_direct_wins=a_direct_wins,
            b_direct_wins=b_direct_wins,
            a_direct_sub_avg=a_direct_avg,
            b_direct_sub_avg=b_direct_avg,
            common_opponents=common_opponents,
            a_consistency_std_dev=a_consistency,
            b_consistency_std_dev=b_consistency,
        )

    def _calculate_common_opponents_debater(self, p_a: int, p_b: int) -> List[CommonOpponentRecord]:
        """Find common opponent teams that both debaters faced and summarize records."""
        cur = self.conn.cursor()

        def get_opp_stats(pid: int) -> Dict[str, dict]:
            cur.execute(
                """
                WITH my_debates AS (
                    SELECT DISTINCT debate_id, team_id, side
                    FROM speech_performances
                    WHERE person_id = ?
                )
                SELECT opp.name as opp_name, inst.name as inst_name,
                       COUNT(DISTINCT d.id) as debates,
                       SUM(CASE 
                           WHEN d.is_walkover = 1 AND d.walkover_winner_id = md.team_id THEN 1
                           WHEN (md.side = 'Proposition' AND deb_bal.prop_ballots > deb_bal.opp_ballots)
                             OR (md.side = 'Opposition' AND deb_bal.opp_ballots > deb_bal.prop_ballots) THEN 1
                           ELSE 0 END) as wins,
                       AVG(CASE WHEN md.side = 'Proposition' THEN deb_bal.prop_margin ELSE -deb_bal.prop_margin END) as avg_margin
                FROM my_debates md
                JOIN debates d ON md.debate_id = d.id
                JOIN teams opp ON ((d.prop_team_id = md.team_id AND d.opp_team_id = opp.id)
                                OR (d.opp_team_id = md.team_id AND d.prop_team_id = opp.id))
                LEFT JOIN institutions inst ON opp.institution_id = inst.id
                LEFT JOIN (
                    SELECT debate_id,
                           SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                           SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                           AVG(prop_total_score - opp_total_score) as prop_margin
                    FROM adjudicator_ballots
                    GROUP BY debate_id
                ) deb_bal ON d.id = deb_bal.debate_id
                GROUP BY opp.name
                """,
                (pid,),
            )
            res = {}
            for r in cur.fetchall():
                cnt = r["debates"]
                w = r["wins"] or 0
                pct = round((w / cnt * 100.0), 5) if cnt > 0 else 0.0
                margin = round(float(r["avg_margin"]), 5) if r["avg_margin"] is not None else None
                res[r["opp_name"]] = {
                    "institution": r["inst_name"],
                    "debates": cnt,
                    "wins": w,
                    "win_pct": pct,
                    "avg_margin": margin,
                }
            return res

        stats_a = get_opp_stats(p_a)
        stats_b = get_opp_stats(p_b)

        common_keys = set(stats_a.keys()).intersection(set(stats_b.keys()))
        records: List[CommonOpponentRecord] = []

        for opp_name in sorted(common_keys):
            a_data = stats_a[opp_name]
            b_data = stats_b[opp_name]
            records.append(
                CommonOpponentRecord(
                    opponent_name=opp_name,
                    opponent_institution=a_data["institution"] or b_data["institution"],
                    a_debates=a_data["debates"],
                    a_wins=a_data["wins"],
                    a_win_pct=a_data["win_pct"],
                    a_avg_margin=a_data["avg_margin"],
                    b_debates=b_data["debates"],
                    b_wins=b_data["wins"],
                    b_win_pct=b_data["win_pct"],
                    b_avg_margin=b_data["avg_margin"],
                )
            )

        # Sort by total debates against common opponents
        records.sort(key=lambda r: (r.a_debates + r.b_debates), reverse=True)
        return records

    def compare_teams(self, team_name_a: str, team_name_b: str) -> Optional[TeamHeadToHead]:
        """Generate head-to-head comparison between two teams."""
        cur = self.conn.cursor()

        # Check institutions for Team A and Team B
        cur.execute("SELECT DISTINCT inst.name FROM teams t JOIN institutions inst ON t.institution_id = inst.id WHERE t.name LIKE ?", (f"{team_name_a}%",))
        inst_a_rows = cur.fetchall()
        inst_a = ", ".join(r[0] for r in inst_a_rows) if inst_a_rows else "Unknown Institution"

        cur.execute("SELECT DISTINCT inst.name FROM teams t JOIN institutions inst ON t.institution_id = inst.id WHERE t.name LIKE ?", (f"{team_name_b}%",))
        inst_b_rows = cur.fetchall()
        inst_b = ", ".join(r[0] for r in inst_b_rows) if inst_b_rows else "Unknown Institution"

        # 1. Direct Debates between Team A and Team B
        cur.execute(
            """
            SELECT d.id as debate_id, t.name as tour_name, t.slug as tour_slug,
                   r.round_number, r.name as round_name, r.round_type,
                   t1.name as prop_team_name, t2.name as opp_team_name,
                   d.prop_team_id, d.opp_team_id,
                   d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots, deb_bal.prop_margin
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
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
            WHERE (t1.name LIKE ? AND t2.name LIKE ?)
               OR (t1.name LIKE ? AND t2.name LIKE ?)
            ORDER BY t.id, r.round_number
            """,
            (f"{team_name_a}%", f"{team_name_b}%", f"{team_name_b}%", f"{team_name_a}%"),
        )
        debate_rows = cur.fetchall()

        direct_matches: List[DirectDebateMatchup] = []
        a_direct_wins = 0
        b_direct_wins = 0
        a_margins: List[float] = []
        b_margins: List[float] = []

        for row in debate_rows:
            prop_n = row["prop_team_name"]
            opp_n = row["opp_team_name"]

            a_is_prop = team_name_a.lower() in prop_n.lower()
            side_a = "Proposition" if a_is_prop else "Opposition"
            side_b = "Opposition" if a_is_prop else "Proposition"

            p_bal = row["prop_ballots"] or 0
            o_bal = row["opp_ballots"] or 0
            is_wo = bool(row["is_walkover"])

            if is_wo:
                winner_id = row["walkover_winner_id"]
                a_id = row["prop_team_id"] if a_is_prop else row["opp_team_id"]
                a_won = (winner_id == a_id)
                b_won = not a_won
                split_str = "WALKOVER"
                margin_a = None
            else:
                if a_is_prop:
                    a_won = p_bal > o_bal
                    b_won = o_bal > p_bal
                    margin_a = round(row["prop_margin"], 5) if row["prop_margin"] is not None else None
                else:
                    a_won = o_bal > p_bal
                    b_won = p_bal > o_bal
                    margin_a = round(-row["prop_margin"], 5) if row["prop_margin"] is not None else None
                split_str = f"{max(p_bal, o_bal)}-{min(p_bal, o_bal)}"

            if a_won:
                a_direct_wins += 1
                winner_n = prop_n if a_is_prop else opp_n
                if margin_a is not None:
                    a_margins.append(margin_a)
            elif b_won:
                b_direct_wins += 1
                winner_n = opp_n if a_is_prop else prop_n
                if margin_a is not None:
                    b_margins.append(-margin_a)
            else:
                winner_n = "Draw"

            direct_matches.append(
                DirectDebateMatchup(
                    debate_id=row["debate_id"],
                    tournament_name=row["tour_name"],
                    tournament_slug=row["tour_slug"],
                    round_number=row["round_number"],
                    round_name=row["round_name"],
                    round_type=row["round_type"],
                    team_a_name=prop_n if a_is_prop else opp_n,
                    team_b_name=opp_n if a_is_prop else prop_n,
                    side_a=side_a,
                    side_b=side_b,
                    is_walkover=is_wo,
                    winner_team_name=winner_n,
                    a_won=a_won,
                    b_won=b_won,
                    ballot_split=split_str,
                    margin_a=margin_a,
                )
            )

        # Career metrics for Team A and Team B
        metrics_a = self._get_team_career_metrics(team_name_a)
        metrics_b = self._get_team_career_metrics(team_name_b)

        # Common opponents
        common_opponents = self._calculate_common_opponents_team(team_name_a, team_name_b)

        all_margins_a = [m.margin_a for m in direct_matches if m.margin_a is not None]
        a_avg_margin = round(sum(all_margins_a) / len(all_margins_a), 5) if all_margins_a else None
        b_avg_margin = round(-a_avg_margin, 5) if a_avg_margin is not None else None

        return TeamHeadToHead(
            team_a_name=team_name_a,
            team_b_name=team_name_b,
            institution_a=inst_a,
            institution_b=inst_b,
            direct_debates=direct_matches,
            a_direct_wins=a_direct_wins,
            b_direct_wins=b_direct_wins,
            a_direct_margin_avg=a_avg_margin,
            b_direct_margin_avg=b_avg_margin,
            metrics_a=metrics_a,
            metrics_b=metrics_b,
            common_opponents=common_opponents,
        )

    def _get_team_career_metrics(self, team_name: str) -> dict:
        """Fetch high-level career metrics for a team identity."""
        cur = self.conn.cursor()

        # Check if team exists
        cur.execute("SELECT id, tournament_id FROM teams WHERE name LIKE ?", (f"{team_name}%",))
        team_rows = cur.fetchall()
        if not team_rows:
            return {
                "debates": 0, "wins": 0, "win_pct": 0.0,
                "prop_wins": 0, "prop_debates": 0, "prop_win_pct": 0.0,
                "opp_wins": 0, "opp_debates": 0, "opp_win_pct": 0.0,
                "atss": None, "tournaments": 0, "breaks": 0, "break_pct": 0.0,
            }

        team_ids = {r["id"] for r in team_rows}
        tour_ids = list({r["tournament_id"] for r in team_rows})

        cur.execute(
            """
            WITH my_teams AS (
                SELECT id FROM teams WHERE name LIKE ?
            )
            SELECT d.id, d.prop_team_id, d.opp_team_id, d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots,
                   CASE WHEN d.prop_team_id IN (SELECT id FROM my_teams) THEN 'Proposition' ELSE 'Opposition' END as team_side,
                   CASE WHEN d.prop_team_id IN (SELECT id FROM my_teams) THEN deb_bal.prop_team_score ELSE deb_bal.opp_team_score END as team_score
            FROM debates d
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                       AVG(prop_total_score) as prop_team_score,
                       AVG(opp_total_score) as opp_team_score
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE d.prop_team_id IN (SELECT id FROM my_teams)
               OR d.opp_team_id IN (SELECT id FROM my_teams)
            """,
            (f"{team_name}%",),
        )
        deb_rows = cur.fetchall()

        total_debates = len(deb_rows)
        wins = 0
        prop_deb = 0
        prop_w = 0
        opp_deb = 0
        opp_w = 0
        scores: List[float] = []

        for r in deb_rows:
            side = r["team_side"]
            p_b = r["prop_ballots"] or 0
            o_b = r["opp_ballots"] or 0
            is_wo = bool(r["is_walkover"])

            if is_wo:
                won = (r["walkover_winner_id"] in team_ids)
            else:
                won = (side == "Proposition" and p_b > o_b) or (side == "Opposition" and o_b > p_b)
                if r["team_score"] and float(r["team_score"]) > 0:
                    scores.append(float(r["team_score"]))

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

        win_pct = round(wins / total_debates * 100.0, 5) if total_debates > 0 else 0.0
        prop_win_pct = round(prop_w / prop_deb * 100.0, 5) if prop_deb > 0 else 0.0
        opp_win_pct = round(opp_w / opp_deb * 100.0, 5) if opp_deb > 0 else 0.0
        atss = round(sum(scores) / len(scores), 5) if scores else None

        # Breaks
        breaking_teams = self.profile_engine.critical_engine._get_breaking_teams()
        breaks = sum(1 for tid in tour_ids if (team_name, tid) in breaking_teams)
        break_pct = round(breaks / len(tour_ids) * 100.0, 5) if tour_ids else 0.0

        return {
            "debates": total_debates,
            "wins": wins,
            "win_pct": win_pct,
            "prop_wins": prop_w,
            "prop_debates": prop_deb,
            "prop_win_pct": prop_win_pct,
            "opp_wins": opp_w,
            "opp_debates": opp_deb,
            "opp_win_pct": opp_win_pct,
            "atss": atss,
            "tournaments": len(tour_ids),
            "breaks": breaks,
            "break_pct": break_pct,
        }

    def _calculate_common_opponents_team(self, t_a: str, t_b: str) -> List[CommonOpponentRecord]:
        """Find common opponents both teams have faced."""
        cur = self.conn.cursor()

        def get_team_opp_stats(name: str) -> Dict[str, dict]:
            cur.execute(
                """
                WITH my_teams AS (
                    SELECT id FROM teams WHERE name LIKE ?
                )
                SELECT opp.name as opp_name, inst.name as inst_name,
                       COUNT(DISTINCT d.id) as debates,
                       SUM(CASE 
                           WHEN d.is_walkover = 1 AND d.walkover_winner_id IN (SELECT id FROM my_teams) THEN 1
                           WHEN (d.prop_team_id IN (SELECT id FROM my_teams) AND deb_bal.prop_ballots > deb_bal.opp_ballots)
                             OR (d.opp_team_id IN (SELECT id FROM my_teams) AND deb_bal.opp_ballots > deb_bal.prop_ballots) THEN 1
                           ELSE 0 END) as wins,
                       AVG(CASE WHEN d.prop_team_id IN (SELECT id FROM my_teams) THEN deb_bal.prop_margin ELSE -deb_bal.prop_margin END) as avg_margin
                FROM debates d
                JOIN teams opp ON ((d.prop_team_id IN (SELECT id FROM my_teams) AND d.opp_team_id = opp.id)
                                OR (d.opp_team_id IN (SELECT id FROM my_teams) AND d.prop_team_id = opp.id))
                LEFT JOIN institutions inst ON opp.institution_id = inst.id
                LEFT JOIN (
                    SELECT debate_id,
                           SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                           SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                           AVG(prop_total_score - opp_total_score) as prop_margin
                    FROM adjudicator_ballots
                    GROUP BY debate_id
                ) deb_bal ON d.id = deb_bal.debate_id
                WHERE d.prop_team_id IN (SELECT id FROM my_teams)
                   OR d.opp_team_id IN (SELECT id FROM my_teams)
                GROUP BY opp.name
                """,
                (f"{name}%",),
            )
            res = {}
            for r in cur.fetchall():
                cnt = r["debates"]
                w = r["wins"] or 0
                pct = round((w / cnt * 100.0), 5) if cnt > 0 else 0.0
                margin = round(float(r["avg_margin"]), 5) if r["avg_margin"] is not None else None
                res[r["opp_name"]] = {
                    "institution": r["inst_name"],
                    "debates": cnt,
                    "wins": w,
                    "win_pct": pct,
                    "avg_margin": margin,
                }
            return res

        stats_a = get_team_opp_stats(t_a)
        stats_b = get_team_opp_stats(t_b)

        common_keys = set(stats_a.keys()).intersection(set(stats_b.keys()))
        records: List[CommonOpponentRecord] = []

        for opp_name in sorted(common_keys):
            a_data = stats_a[opp_name]
            b_data = stats_b[opp_name]
            records.append(
                CommonOpponentRecord(
                    opponent_name=opp_name,
                    opponent_institution=a_data["institution"] or b_data["institution"],
                    a_debates=a_data["debates"],
                    a_wins=a_data["wins"],
                    a_win_pct=a_data["win_pct"],
                    a_avg_margin=a_data["avg_margin"],
                    b_debates=b_data["debates"],
                    b_wins=b_data["wins"],
                    b_win_pct=b_data["win_pct"],
                    b_avg_margin=b_data["avg_margin"],
                )
            )

        records.sort(key=lambda r: (r.a_debates + r.b_debates), reverse=True)
        return records
