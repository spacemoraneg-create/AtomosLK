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

from atomos.analytics.tournaments import (
    OFFICIAL_TOURNAMENT_DATES,
    CLEAN_TOURNAMENT_NAMES,
    CHRONOLOGICAL_TOURNAMENT_ORDER,
)


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

CANONICAL_TEAM_ALIASES = {
    "Trinity A": "TCK A",
    "Trinity B": "TCK B",
    "EMS A": "Moir A",
    "Nalanda A": "NC A",
    "Nalanda B": "NC B",
    "Anula A": "AV A",
    "Anula B": "AV B",
    "MC A": "Metho A",
    "SJOC A": "SJCJ A",
    "SGC A": "SGCK A",
    "EC A": "EIK A",
    "EC B": "EIK B",
}

CANONICAL_ADJUDICATOR_ALIASES = {
    "Dineth": "Dineth Keragala",
    "Visura": "Visura Padeniya",
    "Akindu": "Akindu Athauda",
    "Akindu Attauda": "Akindu Athauda",
    "Amnah": "Amnah Jiffrey",
    "amnah jiffrey": "Amnah Jiffrey",
    "Chrishelle": "Chrishelle Perera",
    "Daniel": "Daniel Victor",
    "Esala": "Esala Rajapakse",
    "Esala Rajapakshe": "Esala Rajapakse",
    "Kaveesha Mallawarachchi": "Kaveesha Mallawaarachchi",
    "Kavodi": "Kavodi Kulunumini Ranasinghe",
    "Mevindu": "Mevindu Asuramanna",
    "Naika": "Naika Gooneratne",
    "Naika Goonerathne": "Naika Gooneratne",
    "Nethma": "Nethma Madawala",
    "Nethma Madawela": "Nethma Madawala",
    "Risindu": "Risindu Piyasena",
    "Saara": "Saara Zubair",
    "Sandil": "Sandil Ranasinghe",
    "Sanithma": "Sanithma Jayasooriya",
    "Savidya": "Savidya Akini",
    "Shakeeb": "Shakeeb Mohideen",
    "Shenaya": "Shenaya Rodrigo",
    "Sithma": "Sithma Hewa Waduge",
    "Vihara": "Vihara Fernandopulle",
    "Yaqeen": "Yaqeen Zuresh",
    "Yasindu": "Yasindu Edussuriya",
    "Jayageeth Bassnayake": "Jayageeth Basnayake",
    "Gavin Seneratne": "Gavin Senaratne",
    "Nimansa Jayasundara": "Nimansa Jayasundera",
    "Savith Wijesundera": "Savith Wijesundara",
    "Sarah Warnakalasuriya": "Sarah Warnakulasuriya",
    "Sarah Warnakulasooriya": "Sarah Warnakulasuriya",
    "Thishiya Mendis": "Thishya Mendis",
    "Thishya Mendia": "Thishya Mendis",
    "Tharin Rajapakshe": "Tharin Rajapakse",
    "Zaid B. Hussain": "Zaid Hussain",
    "Buthmini Mohotty": "Buthmini Mohotti",
    "Ra&#x27;ed Abdul Cader": "Ra'ed Abdul Cader",
}


def calc_sample_stdev(values: List[float]) -> float:
    """Calculate sample standard deviation. Returns 0.0 if fewer than 2 values."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return truncate_3(math.sqrt(variance)) or 0.0


def truncate_3(val: Optional[float]) -> Optional[float]:
    """Universal Rule: Do not round up. Up to 3 decimal places if exist."""
    if val is None:
        return None
    try:
        f = float(val)
        if f.is_integer():
            return int(f)
        s = f"{f:.8f}"
        parts = s.split(".")
        truncated = parts[0] + "." + parts[1][:3].rstrip("0")
        if truncated.endswith("."):
            return int(parts[0])
        return float(truncated)
    except Exception:
        return val


class V2MetricsEngine:
    """Engine computing all Atomos V2 analytical and multi-purpose metrics."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def _get_all_team_and_debater_achievements(self) -> Tuple[Dict[int, str], Dict[str, str], Dict[int, str]]:
        """
        Compute forensic knockout stage achievements for:
        1. raw team_id -> achievement
        2. canonical_team_name -> achievement
        3. person_id -> achievement
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.tournament_id, r.round_number, COUNT(d.id) as deb_count, r.id as round_id
            FROM rounds r
            JOIN debates d ON r.id = d.round_id
            WHERE r.round_type = 'ELIMINATION'
            GROUP BY r.id
            ORDER BY r.tournament_id, r.round_number DESC
        """)
        elim_round_rows = cur.fetchall()
        tour_rounds: Dict[int, List[Tuple[int, int, int]]] = {}
        for r in elim_round_rows:
            tour_rounds.setdefault(r["tournament_id"], []).append((r["round_number"], r["deb_count"], r["round_id"]))
        for tid in tour_rounds:
            tour_rounds[tid].sort(key=lambda x: x[0], reverse=True)

        cur.execute("""
            SELECT d.id, r.tournament_id, r.round_number, d.prop_team_id, d.opp_team_id,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as p_bal,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as o_bal
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE r.round_type = 'ELIMINATION'
            GROUP BY d.id
        """)
        debates = cur.fetchall()

        def better_ach(a: Optional[str], b: Optional[str]) -> str:
            if not a:
                return b or "Preliminary Rounds"
            if not b:
                return a
            return a if ACHIEVEMENT_ORDER.get(a, 9) <= ACHIEVEMENT_ORDER.get(b, 9) else b

        raw_team_ach: Dict[int, str] = {}
        for d in debates:
            tid = d["tournament_id"]
            rnum = d["round_number"]
            p_tid = d["prop_team_id"]
            o_tid = d["opp_team_id"]
            p_bal = d["p_bal"] or 0
            o_bal = d["o_bal"] or 0

            t_elims = tour_rounds.get(tid, [])
            gf_round = next((r for r in t_elims if r[1] == 1), t_elims[0] if t_elims else None)

            if gf_round and rnum == gf_round[0]:
                if p_bal > o_bal:
                    p_ach, o_ach = "Champion", "Finalist"
                else:
                    p_ach, o_ach = "Finalist", "Champion"
            else:
                match_r = next((r for r in t_elims if r[0] == rnum), None)
                cnt = match_r[1] if match_r else 0
                if cnt == 2:
                    stage = "Semifinalist"
                elif cnt == 4:
                    stage = "Quarterfinalist"
                elif cnt == 8:
                    stage = "Octofinalist"
                else:
                    stage = "Partial Octofinalist"
                p_ach, o_ach = stage, stage

            if p_tid:
                raw_team_ach[p_tid] = better_ach(raw_team_ach.get(p_tid), p_ach)
            if o_tid:
                raw_team_ach[o_tid] = better_ach(raw_team_ach.get(o_tid), o_ach)

        # Canonical team achievements
        cur.execute("SELECT id, name FROM teams WHERE name NOT LIKE '%Swing%'")
        canonical_team_ach: Dict[str, str] = {}
        for r in cur.fetchall():
            cname = CANONICAL_TEAM_ALIASES.get(r["name"], r["name"])
            tid = r["id"]
            if tid in raw_team_ach:
                canonical_team_ach[cname] = better_ach(canonical_team_ach.get(cname), raw_team_ach[tid])

        # Person achievements
        cur.execute("SELECT DISTINCT person_id, team_id FROM speech_performances WHERE team_id IS NOT NULL")
        person_ach: Dict[int, str] = {}
        for r in cur.fetchall():
            pid = r["person_id"]
            tid = r["team_id"]
            if tid in raw_team_ach:
                person_ach[pid] = better_ach(person_ach.get(pid), raw_team_ach[tid])

        return raw_team_ach, canonical_team_ach, person_ach

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

        _, _, person_ach = self._get_all_team_and_debater_achievements()
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
            win_pct = truncate_3(wins / debates * 100.0) if debates > 0 else 0.0

            speakers.append({
                "person_id": pid,
                "name": name,
                "speaker_name": name,
                "institution": inst,
                "national_level": nat,
                "speaker_score": truncate_3(mean_score),
                "win_percentage": win_pct,
                "stdev": stdev,
                "prelims_debated": speech_count,
                "tournaments_debated": tour_count,
                "total_substantive_speeches": speech_count,
                "total_debates": debates,
                "total_wins": wins,
                "highest_achievement": person_ach.get(pid, "Preliminary Rounds"),
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
            speakers.sort(key=lambda s: (-s["win_percentage"], -(s["speaker_score"] or 0), -s["prelims_debated"]))
        elif sort_by in ("stdev", "std", "consistency"):
            speakers.sort(key=lambda s: (s["stdev"] if s["stdev"] is not None else 999, -(s["speaker_score"] or 0)))
        elif sort_by in ("prelims", "prelims_debated"):
            speakers.sort(key=lambda s: (-s["prelims_debated"], -(s["speaker_score"] or 0)))
        elif sort_by in ("nat_status", "national_level", "nat_pool"):
            speakers.sort(key=lambda s: (nat_rank(s["national_level"]), -(s["speaker_score"] or 0)))
        elif sort_by in ("achievement", "highest_achievement"):
            speakers.sort(key=lambda s: (ACHIEVEMENT_ORDER.get(s["highest_achievement"], 9), -(s["speaker_score"] or 0)))
        else:  # default 'speaker_score'
            speakers.sort(key=lambda s: (-(s["speaker_score"] or 0), -s["win_percentage"], s["stdev"] if s["stdev"] is not None else 999))

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
          - 'atss' (Default): Average Total Speaker Score (Avg of avgs)
          - 'win_pct': Team win rate
          - 'awpt': Average wins per tournament
          - 'achievement': Highest achievement in knockouts
        """
        min_tourneys = 3 if tier == "tab" else 2
        cur = self.conn.cursor()

        raw_team_ach, canonical_team_ach, _ = self._get_all_team_and_debater_achievements()

        # Query all teams with canonical alias mapping
        cur.execute("""
            SELECT t.id, t.name, t.tournament_id, i.name as institution_name
            FROM teams t
            JOIN institutions i ON t.institution_id = i.id
            WHERE t.name NOT LIKE '%Swing%'
        """)
        all_teams = cur.fetchall()

        # Group team IDs by (canonical_name, institution_name)
        grouped_teams: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(lambda: {"team_ids": [], "tournaments": set()})
        for tr in all_teams:
            cname = CANONICAL_TEAM_ALIASES.get(tr["name"], tr["name"])
            key = (cname, tr["institution_name"])
            grouped_teams[key]["team_ids"].append(tr["id"])
            grouped_teams[key]["tournaments"].add(tr["tournament_id"])

        teams_res: List[Dict[str, Any]] = []

        for (cname, inst_name), tdata in grouped_teams.items():
            tourneys_debated = len(tdata["tournaments"])
            if tourneys_debated < min_tourneys:
                continue

            team_ids = tdata["team_ids"]
            placeholders = ",".join("?" * len(team_ids))

            # Fetch all prelim debates contested by this team across tournaments
            cur.execute(f"""
                SELECT d.id as debate_id,
                       r.tournament_id,
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

            # Group match scores by tournament for "Avg of avgs" ATSS calculation
            tour_scores: Dict[int, List[float]] = defaultdict(list)
            all_match_scores: List[float] = []
            total_wins = 0
            prelims_debated = len(debates)

            for deb in debates:
                is_prop = deb["prop_team_id"] in team_ids
                score = deb["prop_avg_score"] if is_prop else deb["opp_avg_score"]
                tid = deb["tournament_id"]

                if score and score > 0:
                    fscore = float(score)
                    all_match_scores.append(fscore)
                    tour_scores[tid].append(fscore)

                # Check win
                won = False
                if deb["is_walkover"] == 1:
                    won = deb["walkover_winner_id"] in team_ids
                else:
                    won = (is_prop and deb["winner_side"] == "Proposition") or (not is_prop and deb["winner_side"] == "Opposition")
                if won:
                    total_wins += 1

            # ATSS per tournament, then average across tournaments ("Avg of avgs")
            tour_atsses = [sum(sc) / len(sc) for sc in tour_scores.values() if sc]
            atss = truncate_3(sum(tour_atsses) / len(tour_atsses)) if tour_atsses else 0.0

            stdev = calc_sample_stdev(all_match_scores)
            win_pct = truncate_3(total_wins / prelims_debated * 100.0) if prelims_debated else 0.0
            awpt = truncate_3(total_wins / tourneys_debated) if tourneys_debated else 0.0
            wins_per_prelim = truncate_3(total_wins / prelims_debated) if prelims_debated else 0.0

            highest_achieve = canonical_team_ach.get(cname, "Preliminary Rounds")

            teams_res.append({
                "team_name": cname,
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
        if sort_by in ("win_pct", "win_percentage", "win_rate"):
            teams_res.sort(key=lambda t: (-t["win_percentage"], -(t["atss"] or 0)))
        elif sort_by in ("awpt", "wins_per_tournament"):
            teams_res.sort(key=lambda t: (-t["awpt"], -(t["atss"] or 0)))
        elif sort_by in ("achievement", "highest_achievement"):
            teams_res.sort(key=lambda t: (t["achievement_rank"], -(t["atss"] or 0)))
        else:  # default 'atss'
            teams_res.sort(key=lambda t: (-(t["atss"] or 0), -t["win_percentage"]))

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
        raw_name = team_name.strip()
        canonical_name = CANONICAL_TEAM_ALIASES.get(raw_name, raw_name)

        # Collect all raw alias names matching this canonical team
        matching_aliases = [k for k, v in CANONICAL_TEAM_ALIASES.items() if v.lower() == canonical_name.lower()]
        matching_aliases.append(canonical_name)

        cur.execute(f"""
            SELECT t.id, t.name, t.tournament_id, i.name as institution_name
            FROM teams t
            JOIN institutions i ON t.institution_id = i.id
            WHERE LOWER(t.name) IN ({','.join('LOWER(?)' for _ in matching_aliases)})
        """, matching_aliases)
        team_instances = cur.fetchall()

        if not team_instances:
            # Fuzzy match
            cur.execute("""
                SELECT t.id, t.name, t.tournament_id, i.name as institution_name
                FROM teams t
                JOIN institutions i ON t.institution_id = i.id
                WHERE t.name LIKE ?
                LIMIT 10
            """, (f"%{raw_name}%",))
            team_instances = cur.fetchall()

        if not team_instances:
            return None

        canonical_team_name = canonical_name
        institution_name = team_instances[0]["institution_name"]
        team_ids = [r["id"] for r in team_instances]
        tourn_to_team_id = {r["tournament_id"]: r["id"] for r in team_instances}
        placeholders = ",".join("?" * len(team_ids))

        raw_team_ach, canonical_team_ach, _ = self._get_all_team_and_debater_achievements()

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
            tour_id = deb["tournament_id"]
            tour_name = CLEAN_TOURNAMENT_NAMES.get(tour_id, deb["tournament_name"])
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

            margin = truncate_3(my_score - opp_score) if my_score and opp_score else 0.0

            # Lineup combination for this debate (substantive speakers only)
            cur.execute(f"""
                SELECT DISTINCT p.canonical_name
                FROM speech_performances sp
                JOIN persons p ON sp.person_id = p.id
                WHERE sp.debate_id = ? AND sp.speech_type = 'SUBSTANTIVE'
                  AND sp.team_id IN ({placeholders})
            """, [deb_id] + team_ids)
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
                    "tournament_id": tour_id,
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
                "team_score": truncate_3(my_score) if my_score else 0.0,
                "opp_score": truncate_3(opp_score) if opp_score else 0.0,
                "margin": margin,
                "result": "Win" if won else "Loss",
                "speakers": speakers,
            })

        # Process lineup rankings
        lineup_list = []
        for lk, lv in lineup_tracker.items():
            l_debates = lv["debates"]
            l_wins = lv["wins"]
            l_win_pct = truncate_3(l_wins / l_debates * 100.0) if l_debates else 0.0
            l_atss = truncate_3(sum(lv["scores"]) / len(lv["scores"])) if lv["scores"] else 0.0
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
            key=lambda x: (-x["win_percentage"], -x["debates"], -(x["atss"] or 0))
        )[:5]

        # Top 5 Highest ATSS Lineups
        top_atss_lineups = sorted(
            [l for l in lineup_list if l["debates"] >= 2] or lineup_list,
            key=lambda x: (-(x["atss"] or 0), -x["win_percentage"], -x["debates"])
        )[:5]

        # Format tournament breakdown list (sorted reverse chronologically)
        tour_breakdown = []
        tour_atss_list = []
        for tslug, tg in sorted(tournament_groups.items(), key=lambda x: CHRONOLOGICAL_TOURNAMENT_ORDER.get(x[1]["tournament_id"], 0), reverse=True):
            t_scores = tg["scores"]
            t_atss = truncate_3(sum(t_scores) / len(t_scores)) if t_scores else 0.0
            if t_scores:
                tour_atss_list.append(sum(t_scores) / len(t_scores))

            tour_id = tg["tournament_id"]
            inst_team_id = tourn_to_team_id.get(tour_id)
            highest_brk = raw_team_ach.get(inst_team_id, "Preliminary Rounds") if inst_team_id else "Preliminary Rounds"

            debates_list = []
            for r in tg["rounds"]:
                debates_list.append({
                    "round_number": r["round_number"],
                    "round_name": r["round_name"],
                    "round_type": r["round_type"],
                    "side": r["side"],
                    "opponent": r["opponent"],
                    "team_score": r["team_score"],
                    "opp_score": r["opp_score"],
                    "margin": r["margin"],
                    "result": r["result"],
                    "won": r["result"] == "Win",
                    "speakers": r["speakers"],
                })

            tour_breakdown.append({
                "tournament_id": tour_id,
                "tournament_name": tg["tournament_name"],
                "slug": tslug,
                "atss": t_atss,
                "tournament_atss": t_atss,
                "wins": tg["wins"],
                "debates_count": tg["debates_count"],
                "highest_stage": highest_brk,
                "highest_break": highest_brk,
                "rounds": debates_list,
                "debates": debates_list,
            })

        top_break_achievements = [
            {
                "tournament_name": t["tournament_name"],
                "tournament_atss": t["tournament_atss"],
                "highest_break": t["highest_break"],
                "slug": t["slug"],
            }
            for t in tour_breakdown
            if t["highest_break"] and t["highest_break"] != "Preliminary Rounds"
        ]
        top_break_achievements.sort(key=lambda x: ACHIEVEMENT_ORDER.get(x["highest_break"], 9))

        overall_atss = truncate_3(sum(tour_atss_list) / len(tour_atss_list)) if tour_atss_list else 0.0
        overall_stdev = calc_sample_stdev(match_scores)
        prelims_total = len(match_scores)
        overall_win_pct = truncate_3(total_wins / len(debates) * 100.0) if debates else 0.0
        awpt = truncate_3(total_wins / len(tournaments_seen)) if tournaments_seen else 0.0
        highest_achieve = canonical_team_ach.get(canonical_team_name, "Preliminary Rounds")

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
            "highest_achievement": highest_achieve,
            "top_break_achievements": top_break_achievements,
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

            # Identify A team and B team records
            a_teams = [t for t in teams if t["name"].endswith(" A") or t["name"].endswith("-A")]
            b_teams = [t for t in teams if t["name"].endswith(" B") or t["name"].endswith("-B")]

            a_team_ids = [t["id"] for t in a_teams]
            b_team_ids = [t["id"] for t in b_teams]

            # Primary canonical team names for display/navigation
            a_team_name = None
            if a_teams:
                first_a = a_teams[0]["name"]
                a_team_name = CANONICAL_TEAM_ALIASES.get(first_a, first_a)

            b_team_name = None
            if b_teams:
                first_b = b_teams[0]["name"]
                b_team_name = CANONICAL_TEAM_ALIASES.get(first_b, first_b)

            # Compute A team ATSS (per-tournament average of averages)
            a_atss = 0.0
            if a_team_ids:
                a_placeholders = ",".join("?" * len(a_team_ids))
                cur.execute(f"""
                    SELECT r.tournament_id,
                           AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as tour_avg
                    FROM debates d
                    JOIN rounds r ON d.round_id = r.id
                    JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
                    JOIN adjudicator_ballots b ON d.id = b.debate_id
                    WHERE t.id IN ({a_placeholders})
                      AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
                    GROUP BY r.tournament_id, d.id
                """, a_team_ids)
                # Group debate averages by tournament
                a_tour_debates: Dict[int, List[float]] = defaultdict(list)
                for row in cur.fetchall():
                    if row["tour_avg"]:
                        a_tour_debates[row["tournament_id"]].append(float(row["tour_avg"]))
                a_tour_atsses = [sum(scores) / len(scores) for scores in a_tour_debates.values() if scores]
                a_atss = truncate_3(sum(a_tour_atsses) / len(a_tour_atsses)) if a_tour_atsses else 0.0

            # Compute B team ATSS (per-tournament average of averages)
            b_atss = None
            if b_team_ids:
                b_placeholders = ",".join("?" * len(b_team_ids))
                cur.execute(f"""
                    SELECT r.tournament_id,
                           AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as tour_avg
                    FROM debates d
                    JOIN rounds r ON d.round_id = r.id
                    JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
                    JOIN adjudicator_ballots b ON d.id = b.debate_id
                    WHERE t.id IN ({b_placeholders})
                      AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
                    GROUP BY r.tournament_id, d.id
                """, b_team_ids)
                b_tour_debates: Dict[int, List[float]] = defaultdict(list)
                for row in cur.fetchall():
                    if row["tour_avg"]:
                        b_tour_debates[row["tournament_id"]].append(float(row["tour_avg"]))
                b_tour_atsses = [sum(scores) / len(scores) for scores in b_tour_debates.values() if scores]
                b_atss = truncate_3(sum(b_tour_atsses) / len(b_tour_atsses)) if b_tour_atsses else None

            # New Delta Formula: (0.8 * A + 1.2 * B) / 2
            b_val = b_atss if b_atss is not None else 0.0
            delta = truncate_3((0.8 * a_atss + 1.2 * b_val) / 2.0)

            net_diff = truncate_3(abs(a_atss - b_atss)) if b_atss is not None else None

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
            win_pct = truncate_3(tot_wins / tot_deb * 100.0) if tot_deb else 0.0

            # Debater Pool: Count of unique debaters from school eligible at least once (>= 3 prelims in a tournament)
            cur.execute("""
                SELECT COUNT(DISTINCT e.person_id) as pool_cnt
                FROM (
                    SELECT sp.person_id
                    FROM speech_performances sp
                    JOIN teams t ON sp.team_id = t.id
                    JOIN rounds r ON sp.round_id = r.id
                    WHERE t.institution_id = ? AND r.round_type = 'PRELIMINARY'
                    GROUP BY sp.person_id, r.tournament_id
                    HAVING COUNT(DISTINCT sp.round_id) >= 3
                ) e
            """, (iid,))
            pool_cnt = cur.fetchone()["pool_cnt"] or 0

            team_names = set(t["name"] for t in teams)

            institutions.append({
                "institution_id": iid,
                "institution_name": iname,
                "code": icode,
                "delta": delta,
                "a_team_name": a_team_name,
                "a_atss": a_atss,
                "b_team_name": b_team_name,
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
            institutions.sort(key=lambda x: (-(x["a_atss"] or 0), -(x["delta"] or 0)))
        elif sort_by == "b_atss":
            # Show institutions with B team first, sorted by B ATSS
            institutions.sort(key=lambda x: (0 if x["b_atss"] is not None else 1, -(x["b_atss"] or 0), -(x["delta"] or 0)))
        elif sort_by == "net_diff":
            # Smallest difference first; schools without B team sorted last
            institutions.sort(key=lambda x: (0 if x["net_diff"] is not None else 1, x["net_diff"] if x["net_diff"] is not None else 999))
        elif sort_by == "win_pct":
            institutions.sort(key=lambda x: (-x["win_percentage"], -(x["delta"] or 0)))
        elif sort_by == "pool":
            institutions.sort(key=lambda x: (-x["pool_count"], -(x["delta"] or 0)))
        else:  # default 'delta'
            institutions.sort(key=lambda x: (-(x["delta"] or 0), -x["win_percentage"]))

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

        # Debater pool details: unique debaters eligible at least once, split into veterans (>= 2 tournaments) vs new (1 tournament)
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
              AND sp.person_id IN (
                  SELECT sp2.person_id
                  FROM speech_performances sp2
                  JOIN teams t2 ON sp2.team_id = t2.id
                  JOIN rounds r2 ON sp2.round_id = r2.id
                  WHERE t2.institution_id = ? AND r2.round_type = 'PRELIMINARY'
                  GROUP BY sp2.person_id, r2.tournament_id
                  HAVING COUNT(DISTINCT sp2.round_id) >= 3
              )
            GROUP BY p.id
            ORDER BY tourneys_count DESC, prelims_count DESC
        """, (iid, iid))
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
            SELECT b.id as ballot_id,
                   b.adjudicator_raw_name,
                   b.adjudicator_institution,
                   r.tournament_id,
                   r.id as round_id,
                   b.winner_side,
                   b.prop_total_score,
                   b.opp_total_score
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            WHERE b.adjudicator_raw_name IS NOT NULL
              AND b.adjudicator_raw_name != ''
              AND b.adjudicator_raw_name NOT LIKE '%Official%'
              AND b.adjudicator_raw_name NOT LIKE '%Scoresheet%'
              AND b.adjudicator_raw_name NOT LIKE '%Tab%'
        """)
        ballot_rows = cur.fetchall()

        judge_data = defaultdict(lambda: {
            "ballot_ids": [],
            "institutions": set(),
            "tournaments": set(),
            "rounds": set(),
            "prop_wins": 0,
            "opp_wins": 0,
            "team_scores": [],
        })

        for br in ballot_rows:
            raw_name = br["adjudicator_raw_name"].strip()
            cname = CANONICAL_ADJUDICATOR_ALIASES.get(raw_name, raw_name)
            j = judge_data[cname]
            j["ballot_ids"].append(br["ballot_id"])
            if br["adjudicator_institution"] and br["adjudicator_institution"].strip():
                j["institutions"].add(br["adjudicator_institution"].strip())
            j["tournaments"].add(br["tournament_id"])
            j["rounds"].add(br["round_id"])
            if br["winner_side"] == "Proposition":
                j["prop_wins"] += 1
            elif br["winner_side"] == "Opposition":
                j["opp_wins"] += 1
            p_s = br["prop_total_score"]
            o_s = br["opp_total_score"]
            if p_s and o_s and p_s > 0 and o_s > 0:
                j["team_scores"].append((float(p_s) + float(o_s)) / 2.0)

        judges: List[Dict[str, Any]] = []

        for jname, jd in judge_data.items():
            ballots_cnt = len(jd["ballot_ids"])
            if ballots_cnt < 2:
                continue

            inst = next(iter(jd["institutions"]), "Independent Adjudicator")

            # AASS: Average Awarded Speaker Score across substantive speeches on their ballots
            placeholders = ",".join("?" * len(jd["ballot_ids"]))
            cur.execute(f"""
                SELECT AVG(total_score)
                FROM speech_performances
                WHERE ballot_id IN ({placeholders})
                  AND speech_type = 'SUBSTANTIVE' AND total_score > 0
            """, jd["ballot_ids"])
            aass_row = cur.fetchone()
            aass = truncate_3(float(aass_row[0])) if aass_row and aass_row[0] else None

            # AATSS: Average Awarded Team Speaker Score
            aatss = truncate_3(sum(jd["team_scores"]) / len(jd["team_scores"])) if jd["team_scores"] else None

            pwins = jd["prop_wins"]
            owins = jd["opp_wins"]
            total_decisions = pwins + owins
            prop_pct = truncate_3((pwins / total_decisions * 100.0)) if total_decisions else 0
            opp_pct = truncate_3((owins / total_decisions * 100.0)) if total_decisions else 0

            judges.append({
                "adjudicator_name": jname,
                "institution": inst,
                "aass": aass,
                "aatss": aatss,
                "prop_wins": pwins,
                "opp_wins": owins,
                "prop_opp_bias": f"{prop_pct}% Prop / {opp_pct}% Opp",
                "prop_bias_pct": prop_pct,
                "opp_bias_pct": opp_pct,
                "prelims_adjudicated": len(jd["rounds"]),
                "tournaments_adjudicated": len(jd["tournaments"]),
                "ballots_count": ballots_cnt,
            })

        judges.sort(key=lambda x: -x["prelims_adjudicated"])
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

        # Prelim + Open Knockout rounds count per tournament
        open_knockout_counts = {1: 5, 2: 3, 3: 4, 4: 4, 7: 4, 10: 4, 16: 3, 18: 3}

        t_results: List[Dict[str, Any]] = []

        for tr in tourneys:
            tid = tr["id"]
            slug = tr["slug"]
            name = CLEAN_TOURNAMENT_NAMES.get(tid, tr["name"])
            dates = OFFICIAL_TOURNAMENT_DATES.get(tid, "2026")

            # 1. Team prelim debate scores within tournament
            cur.execute("""
                SELECT d.id, d.prop_team_id, d.opp_team_id, AVG(b.prop_total_score), AVG(b.opp_total_score)
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY' AND b.prop_total_score > 0
                GROUP BY d.id
            """, (tid,))
            team_scores: Dict[int, List[float]] = {}
            for did, p_tid, o_tid, p_s, o_s in cur.fetchall():
                if p_tid and p_s:
                    team_scores.setdefault(p_tid, []).append(float(p_s))
                if o_tid and o_s:
                    team_scores.setdefault(o_tid, []).append(float(o_s))

            # Team ATSS for each team within tournament
            team_atss = {t_id: sum(scores) / len(scores) for t_id, scores in team_scores.items() if scores}
            atss_val = sum(team_atss.values()) / len(team_atss) if team_atss else 0.0
            atss = truncate_3(atss_val)

            # 2. BRK ATSS: Average ATSS of each team who broke to knockouts in that tournament
            cur.execute("""
                SELECT DISTINCT d.prop_team_id
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND r.round_type = 'ELIMINATION'
                UNION
                SELECT DISTINCT d.opp_team_id
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND r.round_type = 'ELIMINATION'
            """, (tid, tid))
            breaking_team_ids = [r[0] for r in cur.fetchall() if r[0] is not None]

            breaking_atss = [team_atss[t_id] for t_id in breaking_team_ids if t_id in team_atss]
            brk_atss_val = sum(breaking_atss) / len(breaking_atss) if breaking_atss else 0.0
            brk_atss = truncate_3(brk_atss_val)

            # 3. Participating Institutions count
            cur.execute("""
                SELECT COUNT(DISTINCT t.institution_id)
                FROM teams t
                JOIN debates d ON (t.id = d.prop_team_id OR t.id = d.opp_team_id)
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ?
            """, (tid,))
            insts_cnt = cur.fetchone()[0] or 0

            # 4. Participating Teams count (excluding swing)
            cur.execute("""
                SELECT COUNT(DISTINCT t.id)
                FROM teams t
                JOIN debates d ON (t.id = d.prop_team_id OR t.id = d.opp_team_id)
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND t.name NOT LIKE '%Swing%'
            """, (tid,))
            teams_cnt = cur.fetchone()[0] or 0

            # 5. Prelims and Open Break rounds count
            cur.execute("SELECT COUNT(*) FROM rounds WHERE tournament_id = ? AND round_type = 'PRELIMINARY'", (tid,))
            prelim_rds = cur.fetchone()[0] or 0

            open_knock = open_knockout_counts.get(tid, 0)
            prelims_plus_knock = prelim_rds + open_knock

            # 6. Speeches count
            cur.execute("""
                SELECT COUNT(sp.id)
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                WHERE r.tournament_id = ? AND sp.total_score > 0
            """, (tid,))
            speeches_cnt = cur.fetchone()[0] or 0

            # 7. Prelim debates count
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
                "open_knockouts_count": open_knock,
                "prelims_plus_knock": prelims_plus_knock,
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

        spk_avg = truncate_3(sum(sub_scores) / len(sub_scores)) if sub_scores else 0.0
        stdev = truncate_3(calc_sample_stdev(sub_scores))
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
        win_pct = truncate_3(wins / tot_debates * 100.0) if tot_debates else 0.0

        # Speaker position breakdown (1st, 2nd, 3rd) - combination of individual speeches in those spots
        positions = {}
        for pos in ["1st", "2nd", "3rd"]:
            cur.execute("""
                SELECT sp.debate_id, AVG(sp.total_score) as speech_score
                FROM speech_performances sp
                JOIN debates d ON sp.debate_id = d.id
                WHERE sp.person_id = ?
                  AND sp.position = ?
                  AND sp.speech_type = 'SUBSTANTIVE'
                  AND d.is_walkover = 0
                  AND sp.total_score > 0
                GROUP BY sp.debate_id, sp.position
            """, (pid, pos))
            pos_scores = [float(r["speech_score"]) for r in cur.fetchall()]
            avg = truncate_3(sum(pos_scores) / len(pos_scores)) if pos_scores else 0.0
            positions[pos] = {"count": len(pos_scores), "average": avg}

        # Reply speeches - combination of individual reply speeches
        cur.execute("""
            SELECT sp.debate_id, AVG(sp.total_score) as speech_score
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            WHERE sp.person_id = ?
              AND sp.speech_type = 'REPLY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY sp.debate_id, sp.position
        """, (pid,))
        rep_scores = [float(r["speech_score"]) for r in cur.fetchall()]
        rep_avg = truncate_3(sum(rep_scores) / len(rep_scores)) if rep_scores else 0.0
        positions["Reply"] = {"count": len(rep_scores), "average": rep_avg}

        # Tournament breakdown with round-level hover details using verified DebaterProfileEngine
        from atomos.analytics.debater_profile import DebaterProfileEngine
        prof_engine = DebaterProfileEngine(self.conn)
        base_prof = prof_engine.get_profile(pid)

        tournament_breakdown = []
        if base_prof:
            # Reverse chronological order: latest tournament at top (e.g. SLSDC), earliest at bottom (e.g. AISDC)
            sorted_tournaments = sorted(
                base_prof.tournaments,
                key=lambda t: CHRONOLOGICAL_TOURNAMENT_ORDER.get(t.tournament_id, 0),
                reverse=True
            )
            for t in sorted_tournaments:
                tname = CLEAN_TOURNAMENT_NAMES.get(t.tournament_id, t.tournament_name)
                sub_scores = t.prelim_substantive_scores
                t_avg = truncate_3(t.tournament_average) if t.tournament_average is not None else 0.0

                rounds_list = []
                for r in t.prelim_rounds:
                    counted_spk = [sp for sp in r.speeches if sp.is_counted_in_tab]
                    counted_pos = counted_spk[0].position if counted_spk else 'Substantive'
                    judges = list(dict.fromkeys(sp.judge_name for sp in r.speeches if sp.judge_name))
                    judge_str = ', '.join(judges) if judges else 'Adjudication Panel'

                    if r.substantive_score is not None:
                        rounds_list.append({
                            'round_number': r.round_number,
                            'round_name': r.round_name,
                            'round_type': r.round_type,
                            'position': counted_pos,
                            'speech_type': 'SUBSTANTIVE',
                            'score': truncate_3(r.substantive_score),
                            'adjudicator': judge_str,
                            'opponent': r.opp_team_name,
                        })

                    if r.reply_score is not None:
                        rounds_list.append({
                            'round_number': r.round_number,
                            'round_name': r.round_name,
                            'round_type': r.round_type,
                            'position': 'Reply',
                            'speech_type': 'REPLY',
                            'score': truncate_3(r.reply_score),
                            'adjudicator': judge_str,
                            'opponent': r.opp_team_name,
                        })

                tournament_breakdown.append({
                    'tournament_name': tname,
                    'slug': t.tournament_slug,
                    'tournament_average': t_avg,
                    'speeches_count': len(sub_scores),
                    'rounds': rounds_list
                })

        _, _, person_ach = self._get_all_team_and_debater_achievements()

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
            "highest_achievement": person_ach.get(pid, "Preliminary Rounds"),
            "position_averages": positions,
            "tournament_breakdown": tournament_breakdown,
        }
