"""
Atomos V2 Analytics Engine

Implements the V2 Radical Overhaul mathematical specifications:
1. Universal Speaker Score: Weighted arithmetic mean across all substantive speeches
   (strictly excluding replies).
2. Standard Deviation (Stdev): Sample standard deviation of debater substantive speeches
   and team match scores.
3. Multi-Purpose Speaker Leaderboard: Switchable ranking by Speaker Score, Win %,
   Stdev (lower better), Prelims Debated, and Nat Status (3-tier grouping).
4. Multi-Purpose Team Leaderboard: Switchable ranking by ATSS, Win %, AWPT, and
   Highest Break Achievement.
5. Team Bio & Lineup Analytics: Identifies optimal 3-person speaker combinations
   ranked by Top 5 Win % and Top 5 ATSS, plus tournament progressions.
6. Multi-Purpose Institution Leaderboard: Switchable ranking by New Delta
   ((0.8 * A + 1.2 * B) / 2), A-team ATSS, B-team ATSS, Net Diff, Win %, and Debater Pool.
7. Institution Bio: Delta, teams fielded, win rate, debater pool breakdown (veteran vs new).
8. Adjudicator Bio: AASS (Average Awarded Speaker Score), AATSS (Average Awarded Team
   Speaker Score), Prop/Opp win decision bias, prelims & tournaments judged.
9. Hard Tournament Leaderboard: 7 official metrics (ATSS, BRK ATSS, Institutions,
   Teams, Prelims+Open Break Rounds, Speeches, Prelim Debates).
10. National Pool 3-Tier Registry: Unranked clean rosters for Nat Pool Direct,
    Nat Pool Trialed, and Trials.
"""

import math
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from atomos.analytics.tournaments import OFFICIAL_TOURNAMENT_DATES, CLEAN_TOURNAMENT_NAMES


ACHIEVEMENT_ORDER = {
    "Champion": 1,
    "Runners-Up": 2,
    "Finalist": 2,
    "Semifinalist": 3,
    "Quarterfinalist": 4,
    "Partial Octofinalist": 5,
    "Octofinalist": 6,
    "Double Partial Octofinalist": 7,
    "Preliminary Rounds": 8,
    "Unranked": 9,
}


def calc_sample_stdev(values: List[float]) -> float:
    """Calculate sample standard deviation. Returns 0.0 if fewer than 2 values."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return round(math.sqrt(variance), 4)


class V2MetricsEngine:
    """Engine computing all Atomos V2 analytical and multi-purpose metrics."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # =========================================================================
    # 1. MULTI-PURPOSE INDIVIDUAL (DEBATER) LEADERBOARD
    # =========================================================================
    def get_multipurpose_speakers(
        self,
        tier: str = "tab",
        sort_by: str = "speaker_score",
    ) -> List[Dict[str, Any]]:
        """
        Compute multi-purpose debater rankings.
        tier:
          - 'tab' (Default): >= 12 rounds debated
          - 'general': >= 5 rounds debated
          - 'homepage': >= 12 rounds debated
        sort_by:
          - 'speaker_score' (Default): Mean of all substantive speeches
          - 'win_pct': Win rate percentage
          - 'stdev': Standard deviation (ascending: lower is more consistent)
          - 'prelims': Distinct preliminary rounds debated
          - 'nat_status': Nat Pool Direct -> Nat Pool Trialed -> Trials -> None
        """
        min_rounds = 12 if tier in ("tab", "homepage") else 5
        cur = self.conn.cursor()

        # Pre-fetch latest host institutions
        cur.execute("""
            SELECT sp.person_id, inst.name as inst_name
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t ON sp.team_id = t.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE sp.total_score > 0 AND inst.name IS NOT NULL
            ORDER BY tour.id DESC, r.round_number DESC
        """)
        latest_inst: Dict[int, str] = {}
        for row in cur.fetchall():
            pid = row["person_id"]
            if pid not in latest_inst and row["inst_name"]:
                latest_inst[pid] = row["inst_name"]

        # Fetch all preliminary substantive speeches with paneled ballot averaging
        cur.execute("""
            SELECT p.id as person_id,
                   p.canonical_name as speaker_name,
                   p.national_level,
                   r.tournament_id,
                   r.round_number,
                   sp.debate_id,
                   sp.position,
                   AVG(sp.total_score) as round_speech_score
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            JOIN persons p ON sp.person_id = p.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id, r.tournament_id, r.round_number, sp.debate_id, sp.position
            ORDER BY p.id, r.tournament_id, r.round_number
        """)
        rows = cur.fetchall()

        # Iron Man resolution: per person -> tournament -> round, take higher substantive score
        person_rounds: Dict[int, Dict[int, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        person_meta: Dict[int, Dict[str, Any]] = {}

        for r in rows:
            pid = r["person_id"]
            tid = r["tournament_id"]
            rnum = r["round_number"]
            score = float(r["round_speech_score"])
            if pid not in person_meta:
                person_meta[pid] = {
                    "name": r["speaker_name"],
                    "national_level": r["national_level"]
                }
            person_rounds[pid][tid][rnum] = max(person_rounds[pid][tid].get(rnum, 0.0), score)

        # Contested debates and win rate (group by debate to avoid panel ballot multiplication)
        cur.execute("""
            SELECT sp.person_id, d.id as debate_id,
                   MAX(CASE WHEN (d.prop_team_id = sp.team_id AND b.winner_side = 'Proposition') OR
                                 (d.opp_team_id = sp.team_id AND b.winner_side = 'Opposition') OR
                                 (d.is_walkover = 1 AND d.walkover_winner_id = sp.team_id) THEN 1 ELSE 0 END) as won
            FROM debates d
            JOIN speech_performances sp ON d.id = sp.debate_id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE sp.speech_type = 'SUBSTANTIVE'
            GROUP BY sp.person_id, d.id
        """)
        deb_rows = cur.fetchall()
        person_debates: Dict[int, List[int]] = defaultdict(list)
        for r in deb_rows:
            person_debates[r["person_id"]].append(r["won"])

        speakers: List[Dict[str, Any]] = []

        for pid, tours in person_rounds.items():
            all_scores: List[float] = []
            tour_count = len(tours)
            for tid, r_dict in tours.items():
                all_scores.extend(r_dict.values())

            speech_count = len(all_scores)
            if speech_count < min_rounds:
                continue

            mean_score = sum(all_scores) / speech_count
            stdev = calc_sample_stdev(all_scores)

            name = person_meta[pid]["name"]
            nat = person_meta[pid]["national_level"]
            inst = latest_inst.get(pid, "Independent")

            deb_list = person_debates.get(pid, [])
            debates = len(deb_list)
            wins = sum(deb_list)
            win_pct = round((wins / debates * 100.0), 1) if debates > 0 else 0.0

            speakers.append({
                "person_id": pid,
                "name": name,
                "speaker_name": name,
                "institution": inst,
                "national_level": nat,
                "speaker_score": round(mean_score, 5),
                "win_percentage": win_pct,
                "stdev": stdev,
                "prelims_debated": speech_count,
                "tournaments_debated": tour_count,
                "total_substantive_speeches": speech_count,
                "total_debates": debates,
                "total_wins": wins,
            })

        # Apply multi-metric sorting
        def nat_rank(val: Optional[str]) -> int:
            if not val:
                return 4
            v = val.lower()
            if "direct" in v:
                return 1
            if "trialed" in v:
                return 2
            if "trials" in v:
                return 3
            return 4

        if sort_by in ("win_pct", "win_percentage", "win_rate"):
            speakers.sort(key=lambda s: (-s["win_percentage"], -s["speaker_score"], -s["prelims_debated"]))
        elif sort_by in ("stdev", "std", "consistency"):
            speakers.sort(key=lambda s: (s["stdev"], -s["speaker_score"]))
        elif sort_by in ("prelims", "prelims_debated"):
            speakers.sort(key=lambda s: (-s["prelims_debated"], -s["speaker_score"]))
        elif sort_by in ("nat_status", "national_level", "nat_pool"):
            speakers.sort(key=lambda s: (nat_rank(s["national_level"]), -s["speaker_score"]))
        else:  # default 'speaker_score'
            speakers.sort(key=lambda s: (-s["speaker_score"], -s["win_percentage"], s["stdev"]))

        for idx, s in enumerate(speakers, start=1):
            s["rank"] = idx

        return speakers

    # =========================================================================
    # 2. MULTI-PURPOSE TEAM LEADERBOARD & LINEUPS
    # =========================================================================
    def get_multipurpose_teams(
        self,
        tier: str = "tab",
        sort_by: str = "atss",
    ) -> List[Dict[str, Any]]:
        """
        Compute multi-purpose team rankings across circuit teams.
        tier:
          - 'tab' (Default): >= 3 tournaments
          - 'general': >= 2 tournaments
        sort_by:
          - 'atss' (Default): Average Total Speaker Score
          - 'win_pct': Team win rate
          - 'awpt': Average wins per tournament
          - 'achievement': Highest achievement in knockouts
        """
        min_tourneys = 3 if tier == "tab" else 2
        cur = self.conn.cursor()

        # Query all distinct teams that participated in tournaments
        cur.execute("""
            SELECT t.name as team_name,
                   i.name as institution_name,
                   COUNT(DISTINCT t.tournament_id) as tournaments_debated,
                   GROUP_CONCAT(DISTINCT t.id) as team_ids_str
            FROM teams t
            JOIN institutions i ON t.institution_id = i.id
            WHERE t.name NOT LIKE '%Swing%'
            GROUP BY t.name
            HAVING tournaments_debated >= ?
        """, (min_tourneys,))
        team_rows = cur.fetchall()

        teams_res: List[Dict[str, Any]] = []

        for tr in team_rows:
            team_name = tr["team_name"]
            inst_name = tr["institution_name"]
            tourneys_debated = tr["tournaments_debated"]
            team_ids = [int(x) for x in tr["team_ids_str"].split(",") if x]

            # Fetch all prelim debates contested by this team
            placeholders = ",".join("?" * len(team_ids))
            cur.execute(f"""
                SELECT d.id as debate_id,
                       d.round_id,
                       d.prop_team_id,
                       d.opp_team_id,
                       d.is_walkover,
                       d.walkover_winner_id,
                       AVG(b.prop_total_score) as prop_avg_score,
                       AVG(b.opp_total_score) as opp_avg_score,
                       b.winner_side
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE r.round_type = 'PRELIMINARY'
                  AND (d.prop_team_id IN ({placeholders}) OR d.opp_team_id IN ({placeholders}))
                GROUP BY d.id
            """, team_ids + team_ids)
            debates = cur.fetchall()

            if not debates:
                continue

            match_scores: List[float] = []
            total_wins = 0
            prelims_debated = len(debates)

            for deb in debates:
                is_prop = deb["prop_team_id"] in team_ids
                score = deb["prop_avg_score"] if is_prop else deb["opp_avg_score"]
                if score and score > 0:
                    match_scores.append(float(score))

                # Check win
                won = False
                if deb["is_walkover"] == 1:
                    won = deb["walkover_winner_id"] in team_ids
                else:
                    won = (is_prop and deb["winner_side"] == "Proposition") or (not is_prop and deb["winner_side"] == "Opposition")
                if won:
                    total_wins += 1

            atss = round(sum(match_scores) / len(match_scores), 2) if match_scores else 0.0
            stdev = calc_sample_stdev(match_scores)
            win_pct = round((total_wins / prelims_debated * 100.0), 1) if prelims_debated else 0.0
            awpt = round(total_wins / tourneys_debated, 2) if tourneys_debated else 0.0
            wins_per_prelim = round(total_wins / prelims_debated, 2) if prelims_debated else 0.0

            # Determine highest break achievement across all tournaments
            cur.execute(f"""
                SELECT r.round_number, r.name as round_name, t.slug as tournament_slug
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments t ON r.tournament_id = t.id
                WHERE r.round_type = 'ELIMINATION'
                  AND (d.prop_team_id IN ({placeholders}) OR d.opp_team_id IN ({placeholders}))
                ORDER BY r.round_number DESC
            """, team_ids + team_ids)
            elim_debates = cur.fetchall()

            highest_achieve = "Preliminary Rounds"
            if elim_debates:
                max_elim = elim_debates[0]
                r_name = (max_elim["round_name"] or "").lower()
                r_num = max_elim["round_number"]

                # Check if they won the Grand Final
                is_champ = False
                for ed in elim_debates:
                    ed_name = (ed["round_name"] or "").lower()
                    if "final" in ed_name or "round 10" in ed_name or "round 11" in ed_name or "round 12" in ed_name:
                        cur.execute("""
                            SELECT b.winner_side, d.prop_team_id, d.opp_team_id
                            FROM adjudicator_ballots b
                            JOIN debates d ON b.debate_id = d.id
                            JOIN rounds r ON d.round_id = r.id
                            WHERE r.tournament_id = (SELECT id FROM tournaments WHERE slug = ?)
                              AND r.round_type = 'ELIMINATION'
                            ORDER BY r.round_number DESC LIMIT 1
                        """, (ed["tournament_slug"],))
                        gf = cur.fetchone()
                        if gf:
                            winner_team_id = gf["prop_team_id"] if gf["winner_side"] == "Proposition" else gf["opp_team_id"]
                            if winner_team_id in team_ids:
                                is_champ = True
                                break

                if is_champ:
                    highest_achieve = "Champion"
                elif "final" in r_name or r_num >= 10:
                    highest_achieve = "Finalist"
                elif "semi" in r_name or r_num >= 8:
                    highest_achieve = "Semifinalist"
                elif "quarter" in r_name or r_num >= 7:
                    highest_achieve = "Quarterfinalist"
                elif "octo" in r_name or r_num >= 6:
                    highest_achieve = "Octofinalist"
                else:
                    highest_achieve = "Elimination Outrounds"

            teams_res.append({
                "team_name": team_name,
                "institution": inst_name,
                "atss": atss,
                "win_percentage": win_pct,
                "awpt": awpt,
                "wins_per_prelim": wins_per_prelim,
                "stdev": stdev,
                "tournaments_debated": tourneys_debated,
                "prelims_debated": prelims_debated,
                "total_wins": total_wins,
                "highest_achievement": highest_achieve,
                "achievement_rank": ACHIEVEMENT_ORDER.get(highest_achieve, 8),
            })

        # Multi-metric sorting
        if sort_by == "win_pct":
            teams_res.sort(key=lambda t: (-t["win_percentage"], -t["atss"]))
        elif sort_by == "awpt":
            teams_res.sort(key=lambda t: (-t["awpt"], -t["atss"]))
        elif sort_by == "achievement":
            teams_res.sort(key=lambda t: (t["achievement_rank"], -t["atss"]))
        else:  # default 'atss'
            teams_res.sort(key=lambda t: (-t["atss"], -t["win_percentage"]))

        for idx, t in enumerate(teams_res, start=1):
            t["rank"] = idx

        return teams_res

    # =========================================================================
    # 3. TEAM BIO & LINEUP ANALYSIS
    # =========================================================================
    def get_team_bio(self, team_name: str) -> Optional[Dict[str, Any]]:
        """
        Compute deep forensic profile for a team including optimal 3-person
        lineup combinations and tournament-by-tournament breakdowns.
        """
        cur = self.conn.cursor()

        # Find team records matching name
        cur.execute("""
            SELECT t.id, t.name, t.tournament_id, i.name as institution_name
            FROM teams t
            JOIN institutions i ON t.institution_id = i.id
            WHERE LOWER(t.name) = LOWER(?)
        """, (team_name.strip(),))
        team_instances = cur.fetchall()
        if not team_instances:
            # Fuzzy match
            cur.execute("""
                SELECT t.id, t.name, t.tournament_id, i.name as institution_name
                FROM teams t
                JOIN institutions i ON t.institution_id = i.id
                WHERE t.name LIKE ?
                LIMIT 5
            """, (f"%{team_name.strip()}%",))
            team_instances = cur.fetchall()

        if not team_instances:
            return None

        canonical_team_name = team_instances[0]["name"]
        institution_name = team_instances[0]["institution_name"]
        team_ids = [r["id"] for r in team_instances]
        placeholders = ",".join("?" * len(team_ids))

        # Query all debates
        cur.execute(f"""
            SELECT d.id as debate_id,
                   d.round_id,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   t_tour.id as tournament_id,
                   t_tour.slug as tournament_slug,
                   t_tour.name as tournament_name,
                   d.prop_team_id,
                   d.opp_team_id,
                   tp.name as prop_name,
                   topp.name as opp_name,
                   d.is_walkover,
                   d.walkover_winner_id,
                   AVG(b.prop_total_score) as prop_s,
                   AVG(b.opp_total_score) as opp_s,
                   b.winner_side
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t_tour ON r.tournament_id = t_tour.id
            LEFT JOIN teams tp ON d.prop_team_id = tp.id
            LEFT JOIN teams topp ON d.opp_team_id = topp.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE (d.prop_team_id IN ({placeholders}) OR d.opp_team_id IN ({placeholders}))
            GROUP BY d.id
            ORDER BY t_tour.id ASC, r.round_number ASC
        """, team_ids + team_ids)
        debates = cur.fetchall()

        match_scores: List[float] = []
        total_wins = 0
        tournaments_seen = set()
        tournament_groups: Dict[str, Dict[str, Any]] = {}
        lineup_tracker: Dict[str, Dict[str, Any]] = {}

        for deb in debates:
            deb_id = deb["debate_id"]
            tour_slug = deb["tournament_slug"]
            tour_name = CLEAN_TOURNAMENT_NAMES.get(deb["tournament_id"], deb["tournament_name"])
            tournaments_seen.add(tour_slug)

            is_prop = deb["prop_team_id"] in team_ids
            my_score = deb["prop_s"] if is_prop else deb["opp_s"]
            opp_score = deb["opp_s"] if is_prop else deb["prop_s"]
            opp_name = deb["opp_name"] if is_prop else deb["prop_name"]
            my_side = "Proposition" if is_prop else "Opposition"

            if my_score and my_score > 0 and deb["round_type"] == "PRELIMINARY":
                match_scores.append(float(my_score))

            won = False
            if deb["is_walkover"] == 1:
                won = deb["walkover_winner_id"] in team_ids
            else:
                won = (is_prop and deb["winner_side"] == "Proposition") or (not is_prop and deb["winner_side"] == "Opposition")
            if won:
                total_wins += 1

            margin = round((my_score - opp_score), 2) if my_score and opp_score else 0.0

            # Lineup combination for this debate (substantive speakers only)
            cur.execute("""
                SELECT DISTINCT p.canonical_name
                FROM speech_performances sp
                JOIN persons p ON sp.person_id = p.id
                WHERE sp.debate_id = ? AND sp.speech_type = 'SUBSTANTIVE'
                  AND sp.team_id IN ({})
            """.format(placeholders), [deb_id] + team_ids)
            spk_rows = cur.fetchall()
            speakers = sorted([r["canonical_name"] for r in spk_rows if r["canonical_name"]])

            if len(speakers) == 3:
                lineup_key = ", ".join(speakers)
                if lineup_key not in lineup_tracker:
                    lineup_tracker[lineup_key] = {"debates": 0, "wins": 0, "scores": [], "speakers": speakers}
                lineup_tracker[lineup_key]["debates"] += 1
                if won:
                    lineup_tracker[lineup_key]["wins"] += 1
                if my_score:
                    lineup_tracker[lineup_key]["scores"].append(float(my_score))

            # Add to tournament breakdown
            if tour_slug not in tournament_groups:
                tournament_groups[tour_slug] = {
                    "tournament_name": tour_name,
                    "slug": tour_slug,
                    "scores": [],
                    "wins": 0,
                    "debates_count": 0,
                    "stages_reached": [],
                    "rounds": []
                }

            if my_score and deb["round_type"] == "PRELIMINARY":
                tournament_groups[tour_slug]["scores"].append(float(my_score))
            if won:
                tournament_groups[tour_slug]["wins"] += 1
            tournament_groups[tour_slug]["debates_count"] += 1
            tournament_groups[tour_slug]["stages_reached"].append(deb["round_name"])

            tournament_groups[tour_slug]["rounds"].append({
                "round_number": deb["round_number"],
                "round_name": deb["round_name"],
                "round_type": deb["round_type"],
                "side": my_side,
                "opponent": opp_name or "TBD",
                "team_score": round(my_score, 2) if my_score else 0.0,
                "opp_score": round(opp_score, 2) if opp_score else 0.0,
                "margin": margin,
                "result": "Win" if won else "Loss",
                "speakers": speakers,
            })

        # Process lineup rankings
        lineup_list = []
        for lk, lv in lineup_tracker.items():
            l_debates = lv["debates"]
            l_wins = lv["wins"]
            l_win_pct = round((l_wins / l_debates * 100.0), 1) if l_debates else 0.0
            l_atss = round(sum(lv["scores"]) / len(lv["scores"]), 2) if lv["scores"] else 0.0
            lineup_list.append({
                "lineup_str": lk,
                "lineup": lv["speakers"],
                "speakers": lv["speakers"],
                "debates": l_debates,
                "debates_count": l_debates,
                "wins": l_wins,
                "win_percentage": l_win_pct,
                "atss": l_atss,
            })

        # Top 5 Win % Lineups (min 2 debates prioritized)
        top_win_lineups = sorted(
            [l for l in lineup_list if l["debates"] >= 2] or lineup_list,
            key=lambda x: (-x["win_percentage"], -x["debates"], -x["atss"])
        )[:5]

        # Top 5 Highest ATSS Lineups
        top_atss_lineups = sorted(
            [l for l in lineup_list if l["debates"] >= 2] or lineup_list,
            key=lambda x: (-x["atss"], -x["win_percentage"], -x["debates"])
        )[:5]

        # Format tournament breakdown list
        tour_breakdown = []
        for tslug, tg in tournament_groups.items():
            t_scores = tg["scores"]
            t_atss = round(sum(t_scores) / len(t_scores), 2) if t_scores else 0.0
            # Highest stage in knockouts
            knock_stages = [s for s in tg["stages_reached"] if any(w in s.lower() for w in ["round 6", "round 7", "round 8", "round 9", "round 10", "round 11", "round 12", "final", "semi", "quarter", "octo"])]
            stage_str = knock_stages[-1] if knock_stages else "Preliminary Rounds"
            tour_breakdown.append({
                "tournament_name": tg["tournament_name"],
                "slug": tslug,
                "atss": t_atss,
                "wins": tg["wins"],
                "debates_count": tg["debates_count"],
                "highest_stage": stage_str,
                "rounds": tg["rounds"],
            })

        overall_atss = round(sum(match_scores) / len(match_scores), 2) if match_scores else 0.0
        overall_stdev = calc_sample_stdev(match_scores)
        prelims_total = len(match_scores)
        overall_win_pct = round((total_wins / len(debates) * 100.0), 1) if debates else 0.0
        awpt = round(total_wins / len(tournaments_seen), 2) if tournaments_seen else 0.0

        return {
            "team_name": canonical_team_name,
            "institution": institution_name,
            "atss": overall_atss,
            "win_percentage": overall_win_pct,
            "stdev": overall_stdev,
            "prelims_debated": prelims_total,
            "tournaments_debated": len(tournaments_seen),
            "total_debates": len(debates),
            "total_wins": total_wins,
            "wins_per_tournament": awpt,
            "top_win_lineups": top_win_lineups,
            "top_atss_lineups": top_atss_lineups,
            "tournament_breakdown": tour_breakdown,
        }

    # =========================================================================
    # 4. MULTI-PURPOSE INSTITUTION LEADERBOARD & INSTITUTION BIO
    # =========================================================================
    def get_multipurpose_institutions(
        self,
        tier: str = "tab",
        sort_by: str = "delta",
    ) -> List[Dict[str, Any]]:
        """
        Compute multi-purpose institution rankings.
        New Delta Formula:
          Delta = (0.8 * A_ATSS + 1.2 * B_ATSS) / 2.0
          (Always divide by 2, regardless of B-team existence)
        tier:
          - 'tab' (Default): >= 3 tournaments
          - 'general': >= 2 tournaments
        sort_by:
          - 'delta' (Default)
          - 'a_atss'
          - 'b_atss'
          - 'net_diff' (smallest to highest)
          - 'win_pct'
          - 'pool'
        """
        min_tourneys = 3 if tier == "tab" else 2
        cur = self.conn.cursor()

        # Query all active institutions
        cur.execute("""
            SELECT i.id, i.name, i.code
            FROM institutions i
            JOIN teams t ON i.id = t.institution_id
            WHERE i.name NOT LIKE '%Swing%' AND i.name NOT LIKE '%Independent%'
            GROUP BY i.id
        """)
        inst_rows = cur.fetchall()

        institutions: List[Dict[str, Any]] = []

        for ir in inst_rows:
            iid = ir["id"]
            iname = ir["name"]
            icode = ir["code"]

            # Query all teams of this school
            cur.execute("""
                SELECT id, name, tournament_id
                FROM teams
                WHERE institution_id = ? AND name NOT LIKE '%Swing%'
            """, (iid,))
            teams = cur.fetchall()
            if not teams:
                continue

            unique_tourneys = len(set(t["tournament_id"] for t in teams))
            if unique_tourneys < min_tourneys:
                continue

            # Identify A team and B team
            team_names = set(t["name"] for t in teams)
            a_team_name = next((n for n in team_names if n.endswith(" A")), None) or f"{iname} A"
            b_team_name = next((n for n in team_names if n.endswith(" B")), None) or f"{iname} B"

            # Compute A team ATSS
            cur.execute("""
                SELECT AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as match_avg
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
                JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE t.institution_id = ? AND t.name = ?
                  AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
                GROUP BY d.id
            """, (iid, a_team_name))
            a_scores = [float(r["match_avg"]) for r in cur.fetchall() if r["match_avg"]]
            a_atss = round(sum(a_scores) / len(a_scores), 2) if a_scores else 0.0

            # Compute B team ATSS
            cur.execute("""
                SELECT AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as match_avg
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
                JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE t.institution_id = ? AND t.name = ?
                  AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
                GROUP BY d.id
            """, (iid, b_team_name))
            b_scores = [float(r["match_avg"]) for r in cur.fetchall() if r["match_avg"]]
            b_atss = round(sum(b_scores) / len(b_scores), 2) if b_scores else None

            # New Delta Formula: (0.8 * A + 1.2 * B) / 2
            b_val = b_atss if b_atss else 0.0
            delta = round((0.8 * a_atss + 1.2 * b_val) / 2.0, 2)

            net_diff = round(abs(a_atss - b_atss), 2) if b_atss is not None else None

            # Win % across all teams of this school
            cur.execute("""
                SELECT COUNT(DISTINCT d.id) as total_debates,
                       SUM(CASE WHEN (d.prop_team_id = t.id AND b.winner_side = 'Proposition') OR
                                     (d.opp_team_id = t.id AND b.winner_side = 'Opposition') OR
                                     (d.is_walkover = 1 AND d.walkover_winner_id = t.id) THEN 1 ELSE 0 END) as wins
                FROM debates d
                JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
                LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE t.institution_id = ?
            """, (iid,))
            w_row = cur.fetchone()
            tot_deb = w_row["total_debates"] or 0
            tot_wins = w_row["wins"] or 0
            win_pct = round((tot_wins / tot_deb * 100.0), 1) if tot_deb else 0.0

            # Debater Pool: Count of unique debaters from school eligible at least once (>= 3 prelims in a tournament)
            cur.execute("""
                SELECT COUNT(DISTINCT sp.person_id) as pool_cnt
                FROM speech_performances sp
                JOIN teams t ON sp.team_id = t.id
                JOIN rounds r ON sp.round_id = r.id
                WHERE t.institution_id = ? AND r.round_type = 'PRELIMINARY'
                GROUP BY sp.person_id, r.tournament_id
                HAVING COUNT(DISTINCT sp.round_id) >= 3
            """, (iid,))
            pool_rows = cur.fetchall()
            pool_cnt = len(pool_rows)

            institutions.append({
                "institution_id": iid,
                "institution_name": iname,
                "code": icode,
                "delta": delta,
                "a_team_name": a_team_name if a_scores else None,
                "a_atss": a_atss if a_scores else 0.0,
                "b_team_name": b_team_name if b_scores else None,
                "b_atss": b_atss,
                "net_diff": net_diff,
                "win_percentage": win_pct,
                "pool_count": pool_cnt,
                "tournaments_debated": unique_tourneys,
                "teams_count": len(team_names),
                "teams_list": sorted(list(team_names)),
            })

        # Apply multi-metric sorting
        if sort_by == "a_atss":
            institutions.sort(key=lambda x: (-x["a_atss"], -x["delta"]))
        elif sort_by == "b_atss":
            # Show institutions with B team first, sorted by B ATSS
            institutions.sort(key=lambda x: (0 if x["b_atss"] is not None else 1, -(x["b_atss"] or 0), -x["delta"]))
        elif sort_by == "net_diff":
            # Smallest difference first; schools without B team sorted last
            institutions.sort(key=lambda x: (0 if x["net_diff"] is not None else 1, x["net_diff"] if x["net_diff"] is not None else 999))
        elif sort_by == "win_pct":
            institutions.sort(key=lambda x: (-x["win_percentage"], -x["delta"]))
        elif sort_by == "pool":
            institutions.sort(key=lambda x: (-x["pool_count"], -x["delta"]))
        else:  # default 'delta'
            institutions.sort(key=lambda x: (-x["delta"], -x["win_percentage"]))

        for idx, inst in enumerate(institutions, start=1):
            inst["rank"] = idx

        return institutions

    def get_institution_bio(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Compute complete dossier for an institution including debater pool."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, name, code
            FROM institutions
            WHERE LOWER(name) = LOWER(?) OR LOWER(code) = LOWER(?)
        """, (identifier.strip(), identifier.strip()))
        row = cur.fetchone()
        if not row:
            cur.execute("""
                SELECT id, name, code
                FROM institutions
                WHERE name LIKE ?
                LIMIT 1
            """, (f"%{identifier.strip()}%",))
            row = cur.fetchone()

        if not row:
            return None

        iid, iname, icode = row["id"], row["name"], row["code"]
        mult_insts = self.get_multipurpose_institutions(tier="general", sort_by="delta")
        inst_meta = next((m for m in mult_insts if m["institution_id"] == iid), None)

        # Debater pool details: distinguish veteran debaters (>= 2 tournaments) vs new debaters (1 tournament)
        cur.execute("""
            SELECT p.id as person_id,
                   p.canonical_name,
                   p.national_level,
                   COUNT(DISTINCT r.tournament_id) as tourneys_count,
                   COUNT(DISTINCT sp.round_id) as prelims_count
            FROM speech_performances sp
            JOIN persons p ON sp.person_id = p.id
            JOIN teams t ON sp.team_id = t.id
            JOIN rounds r ON sp.round_id = r.id
            WHERE t.institution_id = ? AND r.round_type = 'PRELIMINARY'
            GROUP BY p.id
            ORDER BY tourneys_count DESC, prelims_count DESC
        """, (iid,))
        debater_rows = cur.fetchall()

        veterans = []
        new_debaters = []
        for d in debater_rows:
            d_dict = {
                "person_id": d["person_id"],
                "name": d["canonical_name"],
                "national_level": d["national_level"],
                "tournaments": d["tourneys_count"],
                "prelims": d["prelims_count"],
            }
            if d["tourneys_count"] >= 2:
                veterans.append(d_dict)
            else:
                new_debaters.append(d_dict)

        return {
            "institution_id": iid,
            "institution_name": iname,
            "code": icode,
            "delta": inst_meta["delta"] if inst_meta else 0.0,
            "a_team_name": inst_meta["a_team_name"] if inst_meta else None,
            "a_atss": inst_meta["a_atss"] if inst_meta else 0.0,
            "b_team_name": inst_meta["b_team_name"] if inst_meta else None,
            "b_atss": inst_meta["b_atss"] if inst_meta else None,
            "win_percentage": inst_meta["win_percentage"] if inst_meta else 0.0,
            "teams_list": inst_meta["teams_list"] if inst_meta else [],
            "pool_count": len(debater_rows),
            "veterans_count": len(veterans),
            "new_count": len(new_debaters),
            "veterans": veterans,
            "new_debaters": new_debaters,
        }

    # =========================================================================
    # 5. ADJUDICATOR BIO & LEADERBOARD (AASS, AATSS, PROP/OPP BIAS)
    # =========================================================================
    def get_adjudicator_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Compute official circuit adjudicator intelligence profiles:
        - AASS: Average Awarded Speaker Score (strictly substantive speeches)
        - AATSS: Average Awarded Team Speaker Score
        - Prop / Opp Win decision bias
        - Prelims & Tournaments adjudicated
        """
        cur = self.conn.cursor()

        cur.execute("""
            SELECT b.adjudicator_raw_name as judge_name,
                   b.adjudicator_institution as institution,
                   COUNT(b.id) as ballots_count,
                   COUNT(DISTINCT r.tournament_id) as tournaments_adjudicated,
                   COUNT(DISTINCT r.id) as rounds_adjudicated,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_wins,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_wins,
                   AVG(b.prop_total_score) as avg_prop_s,
                   AVG(b.opp_total_score) as avg_opp_s
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            WHERE b.adjudicator_raw_name IS NOT NULL
              AND b.adjudicator_raw_name != ''
              AND b.adjudicator_raw_name NOT LIKE '%Official%'
              AND b.adjudicator_raw_name NOT LIKE '%Scoresheet%'
              AND b.adjudicator_raw_name NOT LIKE '%Tab%'
            GROUP BY b.adjudicator_raw_name
            HAVING ballots_count >= 2
            ORDER BY ballots_count DESC
        """)
        judge_rows = cur.fetchall()

        judges: List[Dict[str, Any]] = []

        for jr in judge_rows:
            jname = jr["judge_name"]
            inst = jr["institution"] or "Independent Adjudicator"
            ballots = jr["ballots_count"]
            tourneys = jr["tournaments_adjudicated"]
            rounds_cnt = jr["rounds_adjudicated"]
            pwins = jr["prop_wins"] or 0
            owins = jr["opp_wins"] or 0

            # AASS: Average Awarded Speaker Score across substantive speeches
            cur.execute("""
                SELECT AVG(sp.total_score) as aass
                FROM speech_performances sp
                JOIN adjudicator_ballots b ON sp.ballot_id = b.id
                WHERE b.adjudicator_raw_name = ?
                  AND sp.speech_type = 'SUBSTANTIVE' AND sp.total_score > 0
            """, (jname,))
            aass_row = cur.fetchone()
            aass = round(float(aass_row["aass"]), 2) if aass_row and aass_row["aass"] else 71.0

            # AATSS: Average Awarded Team Speaker Score (mean of (prop_score + opp_score) / 2)
            cur.execute("""
                SELECT AVG((prop_total_score + opp_total_score) / 2.0) as aatss
                FROM adjudicator_ballots
                WHERE adjudicator_raw_name = ? AND prop_total_score > 0 AND opp_total_score > 0
            """, (jname,))
            aatss_row = cur.fetchone()
            aatss = round(float(aatss_row["aatss"]), 2) if aatss_row and aatss_row["aatss"] else 249.0

            total_decisions = pwins + owins
            prop_pct = round((pwins / total_decisions * 100.0), 1) if total_decisions else 50.0
            opp_pct = round((owins / total_decisions * 100.0), 1) if total_decisions else 50.0

            judges.append({
                "adjudicator_name": jname,
                "institution": inst,
                "aass": aass,
                "aatss": aatss,
                "prop_wins": pwins,
                "opp_wins": owins,
                "prop_opp_bias": f"{prop_pct}% Prop / {opp_pct}% Opp",
                "prop_bias_pct": prop_pct,
                "prelims_adjudicated": rounds_cnt,
                "tournaments_adjudicated": tourneys,
                "ballots_count": ballots,
            })

        for idx, j in enumerate(judges, start=1):
            j["rank"] = idx

        return judges

    def get_adjudicator_bio(self, judge_name: str) -> Optional[Dict[str, Any]]:
        """Fetch bio dossier for an adjudicator."""
        judges = self.get_adjudicator_leaderboard()
        target = next((j for j in judges if j["adjudicator_name"].lower() == judge_name.lower()), None)
        if not target:
            target = next((j for j in judges if judge_name.lower() in j["adjudicator_name"].lower()), None)
        return target

    # =========================================================================
    # 6. HARD TOURNAMENT LEADERBOARD
    # =========================================================================
    def get_tournament_hard_rankings(self, sort_by: str = "atss") -> List[Dict[str, Any]]:
        """
        Compute official tournament hard leaderboard across the 8 circuit tournaments:
        - ATSS: Average team score within tournament
        - BRK ATSS: Average ATSS of breaking teams
        - Participating Institutions count
        - Participating Teams count
        - Prelims + Open Knockout rounds count
        - Speeches count
        - Prelim debates count
        """
        cur = self.conn.cursor()
        cur.execute("SELECT id, slug, name FROM tournaments ORDER BY id ASC")
        tourneys = cur.fetchall()

        t_results: List[Dict[str, Any]] = []

        for tr in tourneys:
            tid = tr["id"]
            slug = tr["slug"]
            name = CLEAN_TOURNAMENT_NAMES.get(tid, tr["name"])
            dates = OFFICIAL_TOURNAMENT_DATES.get(tid, "2026")

            # ATSS: average team score of contested prelim rounds
            cur.execute("""
                SELECT AVG(CASE WHEN sp.side = 'Proposition' THEN b.prop_total_score ELSE b.opp_total_score END) as atss
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN adjudicator_ballots b ON d.id = b.debate_id
                JOIN speech_performances sp ON d.id = sp.debate_id
                WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
            """, (tid,))
            atss_val = cur.fetchone()[0]
            atss = round(float(atss_val), 2) if atss_val else 248.0

            # BRK ATSS: average ATSS of teams that broke to knockouts
            cur.execute("""
                SELECT AVG(b.prop_total_score)
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE r.tournament_id = ? AND r.round_type = 'ELIMINATION' AND b.prop_total_score > 0
            """, (tid,))
            brk_val = cur.fetchone()[0]
            brk_atss = round(float(brk_val), 2) if brk_val else atss + 2.5

            # Participating Institutions
            cur.execute("""
                SELECT COUNT(DISTINCT t.institution_id)
                FROM teams t
                JOIN debates d ON (t.id = d.prop_team_id OR t.id = d.opp_team_id)
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ?
            """, (tid,))
            insts_cnt = cur.fetchone()[0] or 0

            # Participating Teams
            cur.execute("""
                SELECT COUNT(DISTINCT t.id)
                FROM teams t
                JOIN debates d ON (t.id = d.prop_team_id OR t.id = d.opp_team_id)
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND t.name NOT LIKE '%Swing%'
            """, (tid,))
            teams_cnt = cur.fetchone()[0] or 0

            # Prelim rounds and Open Break rounds
            cur.execute("SELECT COUNT(*) FROM rounds WHERE tournament_id = ? AND round_type = 'PRELIMINARY'", (tid,))
            prelim_rds = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM rounds WHERE tournament_id = ? AND round_type = 'ELIMINATION'", (tid,))
            elim_rds = cur.fetchone()[0] or 0

            # Speeches count
            cur.execute("""
                SELECT COUNT(sp.id)
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                WHERE r.tournament_id = ? AND sp.total_score > 0
            """, (tid,))
            speeches_cnt = cur.fetchone()[0] or 0

            # Prelim debates count
            cur.execute("""
                SELECT COUNT(DISTINCT d.id)
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY'
            """, (tid,))
            prelim_debates_cnt = cur.fetchone()[0] or 0

            t_results.append({
                "tournament_id": tid,
                "slug": slug,
                "name": name,
                "hosting_dates": dates,
                "atss": atss,
                "brk_atss": brk_atss,
                "participating_institutions": insts_cnt,
                "participating_teams": teams_cnt,
                "prelims_count": prelim_rds,
                "open_knockouts_count": elim_rds,
                "prelims_plus_knock": prelim_rds + elim_rds,
                "total_speeches": speeches_cnt,
                "prelim_debates": prelim_debates_cnt,
            })

        if sort_by in ("brk_atss", "break_atss"):
            t_results.sort(key=lambda x: -x["brk_atss"])
        elif sort_by in ("institutions", "participating_institutions"):
            t_results.sort(key=lambda x: -x["participating_institutions"])
        elif sort_by in ("teams", "participating_teams"):
            t_results.sort(key=lambda x: -x["participating_teams"])
        elif sort_by in ("prelims_plus_knock", "rounds"):
            t_results.sort(key=lambda x: -x["prelims_plus_knock"])
        elif sort_by in ("total_speeches", "speeches"):
            t_results.sort(key=lambda x: -x["total_speeches"])
        elif sort_by in ("prelim_debates", "debates"):
            t_results.sort(key=lambda x: -x["prelim_debates"])
        else:
            t_results.sort(key=lambda x: -x["atss"])

        for idx, tr in enumerate(t_results, start=1):
            tr["rank"] = idx

        return t_results

    # =========================================================================
    # 7. NATIONAL POOL 3-TIER REGISTRY (UNRANKED)
    # =========================================================================
    def get_national_pool_tiers(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return the 3 official unranked National Contingent rosters:
        1. Nat Pool, Direct
        2. Nat Pool, Trialed
        3. Trials
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT p.id as person_id,
                   p.canonical_name,
                   p.national_level,
                   COALESCE(i.name, 'Independent') as institution
            FROM persons p
            LEFT JOIN (
                SELECT tm.person_id, t.institution_id
                FROM team_members tm
                JOIN teams t ON tm.team_id = t.id
                GROUP BY tm.person_id
            ) primary_inst ON p.id = primary_inst.person_id
            LEFT JOIN institutions i ON primary_inst.institution_id = i.id
            WHERE p.national_level IS NOT NULL
            ORDER BY p.canonical_name ASC
        """)
        rows = cur.fetchall()

        direct: List[Dict[str, Any]] = []
        trialed: List[Dict[str, Any]] = []
        trials: List[Dict[str, Any]] = []

        for r in rows:
            entry = {
                "person_id": r["person_id"],
                "name": r["canonical_name"],
                "institution": r["institution"],
                "national_level": r["national_level"],
            }
            lvl = (r["national_level"] or "").lower()
            if "direct" in lvl:
                direct.append(entry)
            elif "trialed" in lvl:
                trialed.append(entry)
            elif "trials" in lvl:
                trials.append(entry)

        return {
            "nat_pool_direct": direct,
            "nat_pool_trialed": trialed,
            "trials": trials,
            "total_count": len(rows),
        }

    # =========================================================================
    # 8. DEBATER BIO (V2 SPEC)
    # =========================================================================
    def get_debater_v2_profile(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Compute V2 debater profile matching the new spec:
        - Most debated team (with name)
        - Latest representing school
        - 5 Core Metrics: Speaker Avg, Win %, Stdev, Prelims Debated, Tournaments Debated
        - Speaker position graph averages (1st, 2nd, 3rd, Reply)
        - Tournament Breakdown with round-level hover details (opponent, score, judge, position)
        """
        cur = self.conn.cursor()
        is_id = False
        pid = None
        try:
            pid = int(identifier.lstrip("#"))
            is_id = True
        except ValueError:
            pass

        if is_id:
            cur.execute("SELECT id, canonical_name, national_level FROM persons WHERE id = ?", (pid,))
        else:
            cur.execute("SELECT id, canonical_name, national_level FROM persons WHERE LOWER(canonical_name) = LOWER(?)", (identifier.strip(),))
        p_row = cur.fetchone()

        if not p_row and not is_id:
            cur.execute("SELECT id, canonical_name, national_level FROM persons WHERE canonical_name LIKE ? LIMIT 1", (f"%{identifier.strip()}%",))
            p_row = cur.fetchone()

        if not p_row:
            return None

        pid = p_row["id"]
        cname = p_row["canonical_name"]
        nat_lvl = p_row["national_level"]

        # Latest host institution
        cur.execute("""
            SELECT inst.name as inst_name
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t ON sp.team_id = t.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE sp.person_id = ? AND inst.name IS NOT NULL
            ORDER BY tour.id DESC, r.round_number DESC LIMIT 1
        """, (pid,))
        inst_r = cur.fetchone()
        latest_inst = inst_r["inst_name"] if inst_r else "Independent"

        # Most debated team
        cur.execute("""
            SELECT t.name as team_name, COUNT(sp.id) as spk_cnt
            FROM speech_performances sp
            JOIN teams t ON sp.team_id = t.id
            WHERE sp.person_id = ?
            GROUP BY t.id
            ORDER BY spk_cnt DESC LIMIT 1
        """, (pid,))
        tm_r = cur.fetchone()
        most_debated_team = tm_r["team_name"] if tm_r else "Unknown"

        # Preliminary substantive speech scores with paneled ballot averaging and Iron Man resolution
        cur.execute("""
            SELECT r.tournament_id,
                   r.round_number,
                   AVG(sp.total_score) as round_speech_score
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            WHERE sp.person_id = ?
              AND sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY r.tournament_id, r.round_number, sp.debate_id, sp.position
            ORDER BY r.tournament_id, r.round_number
        """, (pid,))
        p_rows = cur.fetchall()

        tour_dict: Dict[int, Dict[int, float]] = defaultdict(dict)
        for pr in p_rows:
            tid = pr["tournament_id"]
            rnum = pr["round_number"]
            score = float(pr["round_speech_score"])
            tour_dict[tid][rnum] = max(tour_dict[tid].get(rnum, 0.0), score)

        sub_scores = []
        for tid, r_dict in tour_dict.items():
            sub_scores.extend(r_dict.values())

        spk_avg = round(sum(sub_scores) / len(sub_scores), 5) if sub_scores else 0.0
        stdev = calc_sample_stdev(sub_scores)
        prelims_cnt = len(sub_scores)
        tourneys_cnt = len(tour_dict)

        # Debates won and total debates (group by debate to avoid panel duplication)
        cur.execute("""
            SELECT d.id,
                   MAX(CASE WHEN (d.prop_team_id = sp.team_id AND b.winner_side = 'Proposition') OR
                                 (d.opp_team_id = sp.team_id AND b.winner_side = 'Opposition') OR
                                 (d.is_walkover = 1 AND d.walkover_winner_id = sp.team_id) THEN 1 ELSE 0 END) as won
            FROM debates d
            JOIN speech_performances sp ON d.id = sp.debate_id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE sp.person_id = ? AND sp.speech_type = 'SUBSTANTIVE'
            GROUP BY d.id
        """, (pid,))
        deb_rows = cur.fetchall()
        tot_debates = len(deb_rows)
        wins = sum(r["won"] for r in deb_rows if r["won"])
        win_pct = round((wins / tot_debates * 100.0), 1) if tot_debates else 0.0

        # Speaker position breakdown (1st, 2nd, 3rd, Reply)
        positions = {}
        for pos in ["1st", "2nd", "3rd"]:
            cur.execute("""
                SELECT total_score
                FROM speech_performances
                WHERE person_id = ? AND position = ? AND speech_type = 'SUBSTANTIVE' AND total_score > 0
            """, (pid, pos))
            pos_scores = [float(r["total_score"]) for r in cur.fetchall()]
            avg = round(sum(pos_scores) / len(pos_scores), 2) if pos_scores else 0.0
            positions[pos] = {"count": len(pos_scores), "average": avg}

        # Reply speeches
        cur.execute("""
            SELECT total_score
            FROM speech_performances
            WHERE person_id = ? AND speech_type = 'REPLY' AND total_score > 0
        """, (pid,))
        rep_scores = [float(r["total_score"]) for r in cur.fetchall()]
        rep_avg = round(sum(rep_scores) / len(rep_scores), 2) if rep_scores else 0.0
        positions["Reply"] = {"count": len(rep_scores), "average": rep_avg}

        # Tournament breakdown with round-level hover details
        cur.execute("""
            SELECT tour.id as tournament_id,
                   tour.slug as tournament_slug,
                   tour.name as tournament_name,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   sp.position,
                   sp.speech_type,
                   sp.total_score,
                   b.adjudicator_raw_name as adjudicator,
                   opp_t.name as opp_team_name
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN debates d ON sp.debate_id = d.id
            LEFT JOIN teams opp_t ON (CASE WHEN d.prop_team_id = sp.team_id THEN d.opp_team_id ELSE d.prop_team_id END) = opp_t.id
            LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
            WHERE sp.person_id = ? AND sp.total_score > 0
            ORDER BY tour.id ASC, r.round_number ASC
        """, (pid,))
        round_entries = cur.fetchall()

        tour_dict = {}
        for re in round_entries:
            tslug = re["tournament_slug"]
            tname = CLEAN_TOURNAMENT_NAMES.get(re["tournament_id"], re["tournament_name"])
            if tslug not in tour_dict:
                tour_dict[tslug] = {
                    "tournament_name": tname,
                    "slug": tslug,
                    "substantive_scores": [],
                    "rounds": []
                }
            if re["speech_type"] == "SUBSTANTIVE":
                tour_dict[tslug]["substantive_scores"].append(float(re["total_score"]))

            tour_dict[tslug]["rounds"].append({
                "round_number": re["round_number"],
                "round_name": re["round_name"],
                "round_type": re["round_type"],
                "position": re["position"],
                "speech_type": re["speech_type"],
                "score": float(re["total_score"]),
                "adjudicator": re["adjudicator"] or "Adjudication Panel",
                "opponent": re["opp_team_name"] or "TBD",
            })

        tournament_breakdown = []
        for tslug, tg in tour_dict.items():
            t_scores = tg["substantive_scores"]
            t_avg = round(sum(t_scores) / len(t_scores), 2) if t_scores else 0.0
            tournament_breakdown.append({
                "tournament_name": tg["tournament_name"],
                "slug": tslug,
                "tournament_average": t_avg,
                "speeches_count": len(t_scores),
                "rounds": tg["rounds"],
            })

        return {
            "person_id": pid,
            "canonical_name": cname,
            "national_level": nat_lvl,
            "latest_institution": latest_inst,
            "most_debated_team": most_debated_team,
            "speaker_avg": spk_avg,
            "speaker_score": spk_avg,
            "win_percentage": win_pct,
            "stdev": stdev,
            "prelims_debated": prelims_cnt,
            "tournaments_debated": tourneys_cnt,
            "total_debates": tot_debates,
            "total_wins": wins,
            "position_averages": positions,
            "tournament_breakdown": tournament_breakdown,
        }
