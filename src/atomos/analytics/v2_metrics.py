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
import re
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
    "Aliza": "Aliza Hussain",
    "Chirathi": "Chirathi Silva",
    "Dinal": "Dinal Wellappili",
    "Okitha": "Okitha Karunadhara",
    "Vakeesh": "Vakeesh Rupan",
    "Raashid": "Raashid Cassim",
    "Nevan": "Nevan Serasundera",
    "Mabroor": "Mabroor Ahmed",
    "Lehara": "Lehara Edirisinghe",
    "Shaluka": "Shaluka Herath",
    "Navidi": "Navidi Perera",
    "Chanidu": "Chanidu Rathnayake",
    "Gimhan": "Gimhan Sooriyabandara",
    "Afly": "Afly Mohamed",
    "Amiru": "Amiru Upekh Gamage",
    "Vidath": "Vidath Marasinghe",
    "Thiseni": "Thiseni Mapa",
    "Shalem": "Shalem Sumanthiran",
    "Husnaa": "Husnaa Imtiaz",
    "Suchith": "Suchith Tissera",
    "Khanavee": "Khanavee Suthaharan",
    "Thahira": "Thahira Saheed",
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
        self._elo_cache: Optional[Dict[str, Dict[Any, Dict[str, Any]]]] = None

    def _get_international_elos(self) -> Dict[str, Dict[Any, Dict[str, Any]]]:
        """Lazily computes and caches the 3-tier International Standard Elo ratings."""
        if self._elo_cache is None:
            from atomos.analytics.ratings import EloRatingEngine
            self._elo_cache = EloRatingEngine(self.conn).compute_all_international_elos()
        return self._elo_cache

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
                r_idx = next((i for i, r in enumerate(t_elims) if r[0] == rnum), None)
                match_r = t_elims[r_idx] if r_idx is not None else None
                cnt = match_r[1] if match_r else 0

                if r_idx == 1:
                    stage = "Semifinalist"
                elif r_idx == 2:
                    stage = "Quarterfinalist"
                elif r_idx == 3:
                    stage = "Partial Octofinalist" if cnt <= 4 else "Octofinalist"
                elif r_idx == 4:
                    stage = "Double Partial Octofinalist" if cnt <= 8 else "Double Octofinalist"
                else:
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

    def _get_break_seeds_map(self) -> Dict[Tuple[str, int], int]:
        """Calculates preliminary seed rank (1 to N) for every breaking team in each tournament."""
        if hasattr(self, "_break_seeds_cache") and self._break_seeds_cache is not None:
            return self._break_seeds_cache

        from atomos.analytics.critical_stats import CriticalStatsEngine
        crit = CriticalStatsEngine(self.conn)
        breaking = crit._get_breaking_teams()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.tournament_id,
                   COALESCE(t.canonical_name, t.name) as team_name,
                   SUM(CASE WHEN (d.prop_team_id = t.id AND b.winner_side = 'Proposition')
                              OR (d.opp_team_id = t.id AND b.winner_side = 'Opposition') THEN 1 ELSE 0 END) as ballots_won,
                   AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as atss,
                   AVG(CASE WHEN d.prop_team_id = t.id THEN b.win_margin ELSE -b.win_margin END) as avg_margin
            FROM teams t
            JOIN debates d ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
            JOIN rounds r ON d.round_id = r.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE r.round_type = 'PRELIMINARY' AND d.is_walkover = 0
            GROUP BY r.tournament_id, COALESCE(t.canonical_name, t.name)
        """)
        tour_teams = defaultdict(list)
        for r in cur.fetchall():
            tour_teams[r[0]].append({"team": r[1], "wins": r[2] or 0, "atss": r[3] or 0.0, "margin": r[4] or 0.0})

        break_seeds: Dict[Tuple[str, int], int] = {}
        for tid, tlist in tour_teams.items():
            tlist.sort(key=lambda x: (x["wins"], x["atss"], x["margin"]), reverse=True)
            for idx, t in enumerate(tlist, 1):
                if (t["team"], tid) in breaking:
                    break_seeds[(t["team"], tid)] = idx
        self._break_seeds_cache = break_seeds
        return break_seeds

    def _calculate_debater_bra(self, person_id: int) -> Tuple[Optional[float], int]:
        break_seeds = self._get_break_seeds_map()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT COALESCE(t.canonical_name, t.name), r.tournament_id
            FROM speech_performances sp
            JOIN teams t ON sp.team_id = t.id
            JOIN rounds r ON sp.round_id = r.id
            WHERE sp.person_id = ?
        """, (person_id,))
        seeds = [break_seeds[(tname, tid)] for tname, tid in cur.fetchall() if (tname, tid) in break_seeds]
        if not seeds:
            return None, 0
        return truncate_3(sum(seeds) / len(seeds)), len(seeds)

    def _calculate_team_bra(self, team_name: str) -> Tuple[Optional[float], int]:
        break_seeds = self._get_break_seeds_map()
        seeds = [seed for (tname, tid), seed in break_seeds.items() if tname.lower() == team_name.lower()]
        if not seeds:
            return None, 0
        return truncate_3(sum(seeds) / len(seeds)), len(seeds)


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
          - 'tab' (Default): >= 18 rounds debated
          - 'general': >= 5 rounds debated
          - 'homepage': >= 18 rounds debated
          - 'all': >= 1 round debated
        sort_by:
          - 'speaker_score' (Default): Mean of all substantive speeches
          - 'win_pct': Win rate percentage
          - 'stdev': Standard deviation (ascending: lower is more consistent)
          - 'prelims': Distinct preliminary rounds debated
          - 'nat_status': Nat Pool Direct -> Nat Pool Trialed -> Trials -> None
        """
        if tier in ("tab", "homepage"):
            min_rounds = 18
        elif tier == "general":
            min_rounds = 5
        else:
            min_rounds = 1
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

        # Pre-fetch most debated team per person
        cur.execute("""
            SELECT sp.person_id, t.name as team_name, COUNT(sp.id) as spk_cnt
            FROM speech_performances sp
            JOIN teams t ON sp.team_id = t.id
            GROUP BY sp.person_id, t.id
            ORDER BY sp.person_id, spk_cnt DESC
        """)
        most_team_map: Dict[int, str] = {}
        for row in cur.fetchall():
            pid = row["person_id"]
            if pid not in most_team_map and row["team_name"]:
                raw_t = row["team_name"]
                most_team_map[pid] = CANONICAL_TEAM_ALIASES.get(raw_t, raw_t)

        # Pre-fetch break seeds per person for BRA
        break_seeds = self._get_break_seeds_map()
        cur.execute("""
            SELECT DISTINCT sp.person_id, COALESCE(t.canonical_name, t.name) as tname, r.tournament_id
            FROM speech_performances sp
            JOIN teams t ON sp.team_id = t.id
            JOIN rounds r ON sp.round_id = r.id
        """)
        person_seeds: Dict[int, List[int]] = defaultdict(list)
        for row in cur.fetchall():
            key = (row["tname"], row["tournament_id"])
            if key in break_seeds:
                person_seeds[row["person_id"]].append(break_seeds[key])

        # Pre-fetch speaker position scores (1st, 2nd, 3rd, Reply) across all non-walkover debates
        cur.execute("""
            SELECT sp.person_id, sp.debate_id, sp.position, sp.speech_type, AVG(sp.total_score) as speech_score
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            WHERE d.is_walkover = 0 AND sp.total_score > 0
            GROUP BY sp.person_id, sp.debate_id, sp.position, sp.speech_type
        """)
        person_pos_scores: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for row in cur.fetchall():
            pid = row["person_id"]
            sc = float(row["speech_score"])
            if row["speech_type"] == "REPLY":
                person_pos_scores[pid]["Reply"].append(sc)
            elif row["speech_type"] == "SUBSTANTIVE" and row["position"] in ("1st", "2nd", "3rd"):
                person_pos_scores[pid][row["position"]].append(sc)

        # Fetch all preliminary speeches (substantive and reply) with paneled ballot averaging & round details
        cur.execute("""
            SELECT p.id as person_id,
                   p.canonical_name as speaker_name,
                   p.national_level,
                   r.tournament_id,
                   tour.name as tournament_name,
                   tour.slug as tournament_slug,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   sp.debate_id,
                   sp.position,
                   sp.speech_type,
                   AVG(sp.total_score) as round_speech_score,
                   CASE WHEN sp.team_id = d.prop_team_id THEN topp.name ELSE tprop.name END as opp_team_name,
                   GROUP_CONCAT(DISTINCT b.adjudicator_raw_name) as judges_raw
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN debates d ON sp.debate_id = d.id
            JOIN persons p ON sp.person_id = p.id
            LEFT JOIN teams tprop ON d.prop_team_id = tprop.id
            LEFT JOIN teams topp ON d.opp_team_id = topp.id
            LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
            WHERE r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id, r.tournament_id, r.round_number, sp.debate_id, sp.position, sp.speech_type
            ORDER BY p.id, r.tournament_id, r.round_number
        """)
        rows = cur.fetchall()

        # Iron Man resolution: per person -> tournament -> round, take higher substantive score
        person_rounds: Dict[int, Dict[int, Dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
        person_tour_details: Dict[int, Dict[int, Dict[str, Any]]] = defaultdict(dict)
        person_meta: Dict[int, Dict[str, Any]] = {}

        for r in rows:
            pid = r["person_id"]
            tid = r["tournament_id"]
            rnum = r["round_number"]
            stype = r["speech_type"]
            score = float(r["round_speech_score"])
            if pid not in person_meta:
                person_meta[pid] = {
                    "name": r["speaker_name"],
                    "national_level": r["national_level"]
                }

            if tid not in person_tour_details[pid]:
                person_tour_details[pid][tid] = {
                    "tournament_id": tid,
                    "tournament_name": CLEAN_TOURNAMENT_NAMES.get(tid, r["tournament_name"]),
                    "slug": r["tournament_slug"],
                    "sub_rounds": {},
                    "reply_rounds": {},
                }

            judges_raw = r["judges_raw"] or ""
            judge_list = [j.strip() for j in judges_raw.split(",") if j.strip() and j.strip() != "Official Tab Reconciled"]
            judge_str = ", ".join(judge_list) if judge_list else "Adjudication Panel"
            opp_name = r["opp_team_name"] or "Opponent"
            rname = r["round_name"] or f"Round {rnum}"

            if stype == "SUBSTANTIVE":
                prev_score = person_rounds[pid][tid].get(rnum, 0.0)
                if score >= prev_score:
                    person_rounds[pid][tid][rnum] = score
                    person_tour_details[pid][tid]["sub_rounds"][rnum] = {
                        "round_number": rnum,
                        "round_name": rname,
                        "round_type": r["round_type"],
                        "position": r["position"] or "Substantive",
                        "speech_type": "SUBSTANTIVE",
                        "score": truncate_3(score),
                        "adjudicator": judge_str,
                        "opponent": opp_name,
                    }
            elif stype == "REPLY":
                prev_rep = person_tour_details[pid][tid]["reply_rounds"].get(rnum)
                if not prev_rep or score >= prev_rep["score"]:
                    person_tour_details[pid][tid]["reply_rounds"][rnum] = {
                        "round_number": rnum,
                        "round_name": rname,
                        "round_type": r["round_type"],
                        "position": "Reply",
                        "speech_type": "REPLY",
                        "score": truncate_3(score),
                        "adjudicator": judge_str,
                        "opponent": opp_name,
                    }

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
        elos = self._get_international_elos()
        debater_elos = elos.get("debaters", {})
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

            d_elo = debater_elos.get(pid, {})
            elo_val = d_elo.get("elo", 1500.0)
            peak_elo_val = d_elo.get("peak_elo", 1500.0)

            p_seeds = person_seeds.get(pid, [])
            bra_val = truncate_3(sum(p_seeds) / len(p_seeds)) if p_seeds else None
            breaks_cnt = len(p_seeds)

            pos_map = person_pos_scores.get(pid, {})
            positions = {}
            for pos_key in ("1st", "2nd", "3rd", "Reply"):
                p_list = pos_map.get(pos_key, [])
                p_avg = truncate_3(sum(p_list) / len(p_list)) if p_list else 0.0
                positions[pos_key] = {"count": len(p_list), "average": p_avg}

            # Build reverse-chronological tournament_breakdown
            tour_breakdown = []
            p_tours = person_tour_details.get(pid, {})
            for tid in sorted(p_tours.keys(), key=lambda t_id: CHRONOLOGICAL_TOURNAMENT_ORDER.get(t_id, 0), reverse=True):
                td = p_tours[tid]
                sub_r_dict = td["sub_rounds"]
                rep_r_dict = td["reply_rounds"]
                if not sub_r_dict:
                    continue
                t_sub_scores = [v["score"] for v in sub_r_dict.values() if v["score"]]
                t_avg = truncate_3(sum(t_sub_scores) / len(t_sub_scores)) if t_sub_scores else 0.0
                rounds_combined = []
                for rnum in sorted(set(list(sub_r_dict.keys()) + list(rep_r_dict.keys()))):
                    if rnum in sub_r_dict:
                        rounds_combined.append(sub_r_dict[rnum])
                    if rnum in rep_r_dict:
                        rounds_combined.append(rep_r_dict[rnum])
                tour_breakdown.append({
                    "tournament_name": td["tournament_name"],
                    "slug": td["slug"],
                    "tournament_average": t_avg,
                    "speeches_count": len(t_sub_scores),
                    "rounds": rounds_combined,
                })

            spk_score = truncate_3(mean_score)
            speakers.append({
                "person_id": pid,
                "name": name,
                "speaker_name": name,
                "canonical_name": name,
                "institution": inst,
                "latest_institution": inst,
                "most_debated_team": most_team_map.get(pid, "Unknown"),
                "national_level": nat,
                "speaker_score": spk_score,
                "speaker_avg": spk_score,
                "elo": elo_val,
                "peak_elo": peak_elo_val,
                "win_percentage": win_pct,
                "stdev": stdev,
                "bra": bra_val,
                "breaks_count": breaks_cnt,
                "prelims_debated": speech_count,
                "tournaments_debated": tour_count,
                "total_substantive_speeches": speech_count,
                "total_debates": debates,
                "total_wins": wins,
                "highest_achievement": person_ach.get(pid, "Preliminary Rounds"),
                "position_averages": positions,
                "tournament_breakdown": tour_breakdown,
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

        if sort_by in ("elo", "rating"):
            speakers.sort(key=lambda s: (-(s["elo"] or 1500.0), -(s["speaker_score"] or 0), -s["win_percentage"]))
        elif sort_by in ("win_pct", "win_percentage", "win_rate"):
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
          - 'all': >= 1 tournament
        sort_by:
          - 'atss' (Default): Average Total Speaker Score (Avg of avgs)
          - 'win_pct': Team win rate
          - 'awpt': Average wins per tournament
          - 'achievement': Highest achievement in knockouts
        """
        if tier == "tab":
            min_tourneys = 3
        elif tier == "general":
            min_tourneys = 2
        else:
            min_tourneys = 1
        cur = self.conn.cursor()

        raw_team_ach, canonical_team_ach, _ = self._get_all_team_and_debater_achievements()
        elos = self._get_international_elos()
        team_elos = elos.get("teams", {})

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
            t_elo = team_elos.get(cname, {})
            elo_val = t_elo.get("elo", 1500.0)
            peak_elo_val = t_elo.get("peak_elo", 1500.0)

            full_bio = self.get_team_bio(cname) or {}

            teams_res.append({
                "team_name": cname,
                "institution": inst_name,
                "atss": atss,
                "elo": elo_val,
                "peak_elo": peak_elo_val,
                "win_percentage": win_pct,
                "awpt": awpt,
                "wins_per_tournament": awpt,
                "wins_per_prelim": wins_per_prelim,
                "stdev": stdev,
                "bra": full_bio.get("bra"),
                "breaks_count": full_bio.get("breaks_count", 0),
                "tournaments_debated": tourneys_debated,
                "prelims_debated": prelims_debated,
                "total_wins": total_wins,
                "highest_achievement": highest_achieve,
                "achievement_rank": ACHIEVEMENT_ORDER.get(highest_achieve, 8),
                "top_break_achievements": full_bio.get("top_break_achievements", []),
                "top_win_lineups": full_bio.get("top_win_lineups", []),
                "top_atss_lineups": full_bio.get("top_atss_lineups", []),
                "tournament_breakdown": full_bio.get("tournament_breakdown", []),
            })

        # Multi-metric sorting
        if sort_by in ("elo", "rating"):
            teams_res.sort(key=lambda t: (-(t["elo"] or 1500.0), -(t["atss"] or 0), -t["win_percentage"]))
        elif sort_by in ("win_pct", "win_percentage", "win_rate"):
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

        # Bulk-fetch all substantive speakers for this team across all its debates
        cur.execute(f"""
            SELECT DISTINCT sp.debate_id, p.canonical_name
            FROM speech_performances sp
            JOIN persons p ON sp.person_id = p.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND sp.team_id IN ({placeholders})
        """, team_ids)
        deb_speakers_map: Dict[int, List[str]] = defaultdict(list)
        for sr in cur.fetchall():
            if sr["canonical_name"]:
                deb_speakers_map[sr["debate_id"]].append(sr["canonical_name"])

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

            speakers = sorted(list(set(deb_speakers_map.get(deb_id, []))))

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

        team_bra, team_breaks = self._calculate_team_bra(canonical_team_name)
        t_elo = self._get_international_elos().get("teams", {}).get(canonical_team_name, {})

        return {
            "team_name": canonical_team_name,
            "institution": institution_name,
            "atss": overall_atss,
            "elo": t_elo.get("elo", 1500.0),
            "peak_elo": t_elo.get("peak_elo", 1500.0),
            "win_percentage": overall_win_pct,
            "stdev": overall_stdev,
            "bra": team_bra,
            "breaks_count": team_breaks,
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
          - 'all': >= 1 tournament
        sort_by:
          - 'delta' (Default)
          - 'a_atss'
          - 'b_atss'
          - 'net_diff' (smallest to highest)
          - 'win_pct'
          - 'pool'
        """
        if tier == "tab":
            min_tourneys = 3
        elif tier == "general":
            min_tourneys = 2
        else:
            min_tourneys = 1
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

            # Debater Pool: unique debaters from school eligible at least once (>= 3 prelims in a tournament)
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
            pool_cnt = len(debater_rows)

            team_names = set(CANONICAL_TEAM_ALIASES.get(t["name"], t["name"]) for t in teams)
            elos = self._get_international_elos()
            inst_elo = elos.get("institutions", {}).get(iid) or elos.get("institutions_by_name", {}).get(iname.lower(), {})
            elo_val = inst_elo.get("elo", 1500.0)
            peak_elo_val = inst_elo.get("peak_elo", 1500.0)

            institutions.append({
                "institution_id": iid,
                "institution_name": iname,
                "code": icode,
                "delta": delta,
                "elo": elo_val,
                "peak_elo": peak_elo_val,
                "a_team_name": a_team_name,
                "a_atss": a_atss,
                "b_team_name": b_team_name,
                "b_atss": b_atss,
                "net_diff": net_diff,
                "win_percentage": win_pct,
                "pool_count": pool_cnt,
                "veterans_count": len(veterans),
                "new_count": len(new_debaters),
                "veterans": veterans,
                "new_debaters": new_debaters,
                "tournaments_debated": unique_tourneys,
                "teams_count": len(team_names),
                "teams_list": sorted(list(team_names)),
            })

        # Apply multi-metric sorting
        if sort_by in ("elo", "rating"):
            institutions.sort(key=lambda x: (-(x["elo"] or 1500.0), -(x["delta"] or 0), -x["win_percentage"]))
        elif sort_by == "a_atss":
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
        mult_insts = self.get_multipurpose_institutions(tier="all", sort_by="delta")
        inst_meta = next((m for m in mult_insts if m["institution_id"] == iid), None)
        if inst_meta:
            return dict(inst_meta)

        elos = self._get_international_elos()
        inst_elo = elos.get("institutions", {}).get(iid) or elos.get("institutions_by_name", {}).get(iname.lower(), {})

        return {
            "institution_id": iid,
            "institution_name": iname,
            "code": icode,
            "delta": 0.0,
            "elo": inst_elo.get("elo", 1500.0),
            "peak_elo": inst_elo.get("peak_elo", 1500.0),
            "a_team_name": None,
            "a_atss": 0.0,
            "b_team_name": None,
            "b_atss": None,
            "win_percentage": 0.0,
            "teams_list": [],
            "pool_count": 0,
            "veterans_count": 0,
            "new_count": 0,
            "veterans": [],
            "new_debaters": [],
        }

    # =========================================================================
    # 5. ADJUDICATOR BIO & LEADERBOARD (AASS, AATSS, PROP/OPP BIAS)
    # =========================================================================
    def get_adjudicator_leaderboard(self, min_prelims: int = 3) -> List[Dict[str, Any]]:
        """
        Compute official circuit adjudicator intelligence profiles:
        - AASS: Average Awarded Speaker Score (strictly substantive speeches)
        - AATSS: Average Awarded Team Speaker Score
        - Prop / Opp Win decision bias
        - Prelims & Tournaments adjudicated
        - Full round-by-round judging_history
        """
        cur = self.conn.cursor()

        cur.execute("""
            SELECT b.id as ballot_id,
                   b.adjudicator_raw_name,
                   b.adjudicator_institution,
                   b.prop_total_score,
                   b.opp_total_score,
                   b.win_margin,
                   b.winner_side,
                   r.id as round_id,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   t.id as tournament_id,
                   t.name as tournament_name,
                   t.slug as tournament_slug,
                   t.hosting_dates as t_hosting_dates,
                   pt.name as prop_team,
                   pi.name as prop_inst,
                   ot.name as opp_team,
                   oi.name as opp_inst
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            LEFT JOIN teams pt ON d.prop_team_id = pt.id
            LEFT JOIN institutions pi ON pt.institution_id = pi.id
            LEFT JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions oi ON ot.institution_id = oi.id
            WHERE b.adjudicator_raw_name IS NOT NULL
              AND b.adjudicator_raw_name != ''
              AND b.adjudicator_raw_name NOT LIKE '%Scoresheet%'
              AND b.adjudicator_raw_name NOT LIKE '%Walkover%'
              AND b.adjudicator_raw_name NOT LIKE '%Tab%'
            ORDER BY t.id ASC, r.round_number ASC
        """)
        ballot_rows = cur.fetchall()

        panel_regex = re.compile(r"Official (?:Panel Decision|Reconstructed)\s*\((.*?)\)", re.IGNORECASE)

        # Precompute ballot history record per ballot_id
        ballot_history_map: Dict[int, Dict[str, Any]] = {}
        for br in ballot_rows:
            b_id = br["ballot_id"]
            raw = br["adjudicator_raw_name"] or ""
            m = panel_regex.search(raw)
            is_panel = False
            panel_members: List[str] = []
            if m:
                is_panel = True
                inner = m.group(1)
                panel_members = [re.sub(r"[^\w\s\.\']", "", n).strip() for n in re.split(r"[,;]|\band\b", inner) if n.strip()]
            t_id = br["tournament_id"]
            t_name = CLEAN_TOURNAMENT_NAMES.get(t_id, br["tournament_name"])
            dates = br["t_hosting_dates"] or OFFICIAL_TOURNAMENT_DATES.get(t_id, "2026")
            ballot_history_map[b_id] = {
                "ballot_id": b_id,
                "tournament_id": t_id,
                "tournament_name": t_name,
                "tournament_slug": br["tournament_slug"],
                "tournament_dates": dates,
                "round_number": br["round_number"],
                "round_name": br["round_name"] or f"Round {br['round_number']}",
                "round_type": br["round_type"],
                "prop_team": CANONICAL_TEAM_ALIASES.get(br["prop_team"], br["prop_team"]) if br["prop_team"] else "Proposition",
                "prop_inst": br["prop_inst"] or "",
                "opp_team": CANONICAL_TEAM_ALIASES.get(br["opp_team"], br["opp_team"]) if br["opp_team"] else "Opposition",
                "opp_inst": br["opp_inst"] or "",
                "winner_side": br["winner_side"],
                "win_margin": br["win_margin"],
                "prop_score": br["prop_total_score"],
                "opp_score": br["opp_total_score"],
                "is_panel": is_panel,
                "panel_members": panel_members,
            }

        judge_data = defaultdict(lambda: {
            "ballot_ids": [],
            "institutions": set(),
            "tournaments": set(),
            "prelim_rounds": set(),
            "outrounds": set(),
            "prop_wins": 0,
            "opp_wins": 0,
            "team_scores": [],
        })

        for br in ballot_rows:
            raw_name = br["adjudicator_raw_name"].strip()
            m = panel_regex.search(raw_name)
            if m:
                inner = m.group(1)
                names = [n.strip() for n in re.split(r"[,;]|\band\b", inner) if n.strip()]
                for n in names:
                    clean_n = re.sub(r"[^\w\s\.\']", "", n).strip()
                    if not clean_n or len(clean_n) < 2:
                        continue
                    cname = CANONICAL_ADJUDICATOR_ALIASES.get(clean_n, clean_n)
                    j = judge_data[cname]
                    j["ballot_ids"].append(br["ballot_id"])
                    if br["adjudicator_institution"] and br["adjudicator_institution"].strip() and br["adjudicator_institution"] != "Tournament Adjudication Core":
                        j["institutions"].add(br["adjudicator_institution"].strip())
                    j["tournaments"].add(br["tournament_id"])
                    if br["round_type"] == "PRELIMINARY":
                        j["prelim_rounds"].add(br["round_id"])
                    else:
                        j["outrounds"].add(br["round_id"])
                    if br["winner_side"] == "Proposition":
                        j["prop_wins"] += 1
                    elif br["winner_side"] == "Opposition":
                        j["opp_wins"] += 1
            elif not any(k in raw_name.lower() for k in ["official", "panel", "scoresheet", "walkover", "tab", "reconciled", "reconstructed"]):
                cname = CANONICAL_ADJUDICATOR_ALIASES.get(raw_name, raw_name)
                j = judge_data[cname]
                j["ballot_ids"].append(br["ballot_id"])
                if br["adjudicator_institution"] and br["adjudicator_institution"].strip():
                    j["institutions"].add(br["adjudicator_institution"].strip())
                j["tournaments"].add(br["tournament_id"])
                if br["round_type"] == "PRELIMINARY":
                    j["prelim_rounds"].add(br["round_id"])
                else:
                    j["outrounds"].add(br["round_id"])
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
            prelims_cnt = len(jd["prelim_rounds"])
            if prelims_cnt < min_prelims:
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

            outrounds_cnt = len(jd["outrounds"])

            # Build judging history for this adjudicator
            seen_b_ids = set()
            history = []
            for b_id in jd["ballot_ids"]:
                if b_id not in seen_b_ids and b_id in ballot_history_map:
                    seen_b_ids.add(b_id)
                    history.append(ballot_history_map[b_id])
            history.sort(key=lambda x: (
                CHRONOLOGICAL_TOURNAMENT_ORDER.get(x["tournament_id"], 99),
                x["round_number"]
            ))

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
                "prelims_adjudicated": prelims_cnt,
                "outrounds_adjudicated": outrounds_cnt,
                "total_rounds_adjudicated": prelims_cnt + outrounds_cnt,
                "tournaments_adjudicated": len(jd["tournaments"]),
                "ballots_count": ballots_cnt,
                "judging_history": history,
            })

        judges.sort(key=lambda x: -x["prelims_adjudicated"])
        for idx, j in enumerate(judges, start=1):
            j["rank"] = idx

        return judges

    def get_adjudicator_bio(self, judge_name: str) -> Optional[Dict[str, Any]]:
        """Fetch bio dossier for an adjudicator with detailed match-level judging history."""
        judges = self.get_adjudicator_leaderboard(min_prelims=0)
        target = next((j for j in judges if j["adjudicator_name"].lower() == judge_name.lower()), None)
        if not target:
            target = next((j for j in judges if judge_name.lower() in j["adjudicator_name"].lower()), None)
        if not target:
            return None
        return dict(target)

    def get_all_h2h_debates(self) -> List[Dict[str, Any]]:
        """Export compact debate clash records so Head-to-Head works 100% accurately in static/GitHub mode."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT d.id as debate_id,
                   t.id as tournament_id,
                   t.name as tournament_name,
                   t.slug as tournament_slug,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   tp.name as prop_team_name,
                   topp.name as opp_team_name,
                   d.is_walkover,
                   d.walkover_winner_id,
                   d.prop_team_id,
                   d.opp_team_id,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            LEFT JOIN teams tp ON d.prop_team_id = tp.id
            LEFT JOIN teams topp ON d.opp_team_id = topp.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            GROUP BY d.id
            ORDER BY t.id ASC, r.round_number ASC
        """)
        debates = cur.fetchall()

        cur.execute("""
            SELECT DISTINCT sp.debate_id, sp.person_id, p.canonical_name, sp.side
            FROM speech_performances sp
            JOIN persons p ON sp.person_id = p.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
        """)
        deb_spk: Dict[int, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: {"Proposition": [], "Opposition": []})
        for sr in cur.fetchall():
            side = sr["side"]
            if side in ("Proposition", "Opposition"):
                deb_spk[sr["debate_id"]][side].append({
                    "person_id": sr["person_id"],
                    "name": sr["canonical_name"],
                })

        result = []
        for row in debates:
            d_id = row["debate_id"]
            spks = deb_spk.get(d_id)
            if not spks or (not spks["Proposition"] and not spks["Opposition"]):
                continue
            p_bal = row["prop_ballots"] or 0
            o_bal = row["opp_ballots"] or 0
            winner_side = None
            if row["is_walkover"]:
                if row["walkover_winner_id"] == row["prop_team_id"]:
                    winner_side = "Proposition"
                elif row["walkover_winner_id"] == row["opp_team_id"]:
                    winner_side = "Opposition"
            else:
                if p_bal > o_bal:
                    winner_side = "Proposition"
                elif o_bal > p_bal:
                    winner_side = "Opposition"

            tid = row["tournament_id"]
            tname = CLEAN_TOURNAMENT_NAMES.get(tid, row["tournament_name"])
            p_team = CANONICAL_TEAM_ALIASES.get(row["prop_team_name"], row["prop_team_name"]) if row["prop_team_name"] else "Proposition"
            o_team = CANONICAL_TEAM_ALIASES.get(row["opp_team_name"], row["opp_team_name"]) if row["opp_team_name"] else "Opposition"

            result.append({
                "debate_id": d_id,
                "tournament_id": tid,
                "tournament_name": tname,
                "tournament_slug": row["tournament_slug"],
                "round_number": row["round_number"],
                "round_name": row["round_name"] or f"Round {row['round_number']}",
                "round_type": row["round_type"],
                "prop_team": p_team,
                "opp_team": o_team,
                "winner_side": winner_side,
                "prop_speakers": spks["Proposition"],
                "opp_speakers": spks["Opposition"],
            })
        return result


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
        cur.execute("SELECT id, slug, name, hosting_dates FROM tournaments ORDER BY id ASC")
        tourneys = cur.fetchall()

        # Prelim + Open Knockout rounds count per tournament
        open_knockout_counts = {1: 5, 2: 3, 3: 4, 4: 4, 7: 4, 10: 4, 16: 3, 18: 3, 44: 4}

        t_results: List[Dict[str, Any]] = []

        for tr in tourneys:
            tid = tr["id"]
            slug = tr["slug"]
            name = CLEAN_TOURNAMENT_NAMES.get(tid, tr["name"])
            dates = tr["hosting_dates"] or OFFICIAL_TOURNAMENT_DATES.get(tid, "2026")

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
    def get_national_pool_tiers(self) -> Dict[str, Any]:
        """
        Return the 3 official National Contingent rosters, ranked within each group
        by Critical Tab average (fallback to normal Tab, then fallback to database substantive average):
        1. Nat Pool, Direct
        2. Nat Pool, Trialed
        3. Trials
        """
        cur = self.conn.cursor()
        from atomos.analytics.critical_stats import CriticalStatsEngine
        from atomos.analytics.master_tabs import MasterTabEngine

        crit_engine = CriticalStatsEngine(self.conn)
        master_engine = MasterTabEngine(self.conn)

        crit_map = {s["person_id"]: s.get("speaker_avg") for s in crit_engine.get_critical_speaker_stats(min_tournaments=3)}
        master_map = {s["person_id"]: s.get("speaker_avg") for s in master_engine.get_master_speaker_tab(min_tournaments=1)}

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
            pid = r["person_id"]
            score = crit_map.get(pid)
            score_src = "Critical Tab"
            if score is None:
                score = master_map.get(pid)
                score_src = "Tab" if score is not None else None

            if score is None:
                cur.execute("""
                    SELECT AVG(sp.total_score)
                    FROM speech_performances sp
                    JOIN rounds r ON sp.round_id = r.id
                    JOIN debates d ON sp.debate_id = d.id
                    WHERE sp.person_id = ?
                      AND sp.speech_type = 'SUBSTANTIVE'
                      AND r.round_type = 'PRELIMINARY'
                      AND d.is_walkover = 0
                      AND sp.total_score > 0
                """, (pid,))
                db_avg = cur.fetchone()[0]
                if db_avg:
                    score = truncate_3(float(db_avg))
                    score_src = "Tab"

            final_score = truncate_3(float(score)) if score is not None else 0.0
            d_elo_pool = self._get_international_elos().get("debaters", {}).get(pid, {})

            entry = {
                "person_id": pid,
                "name": r["canonical_name"],
                "institution": r["institution"],
                "national_level": r["national_level"],
                "speaker_score": final_score,
                "elo": d_elo_pool.get("elo", 1500.0),
                "peak_elo": d_elo_pool.get("peak_elo", 1500.0),
                "score_source": score_src or "Tab",
            }
            lvl = (r["national_level"] or "").lower()
            if "direct" in lvl:
                direct.append(entry)
            elif "trialed" in lvl:
                trialed.append(entry)
            elif "trials" in lvl:
                trials.append(entry)

        # Sort each tier descending by speaker_score and assign rank_in_tier
        for group in (direct, trialed, trials):
            group.sort(key=lambda x: -x["speaker_score"])
            for rank, item in enumerate(group, start=1):
                item["rank_in_tier"] = rank

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
        raw_most_team = tm_r["team_name"] if tm_r else "Unknown"
        most_debated_team = CANONICAL_TEAM_ALIASES.get(raw_most_team, raw_most_team)

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
        debater_bra, debater_breaks = self._calculate_debater_bra(pid)
        d_elo = self._get_international_elos().get("debaters", {}).get(pid, {})

        return {
            "person_id": pid,
            "canonical_name": cname,
            "national_level": nat_lvl,
            "latest_institution": latest_inst,
            "most_debated_team": most_debated_team,
            "speaker_avg": spk_avg,
            "speaker_score": spk_avg,
            "elo": d_elo.get("elo", 1500.0),
            "peak_elo": d_elo.get("peak_elo", 1500.0),
            "win_percentage": win_pct,
            "stdev": stdev,
            "bra": debater_bra,
            "breaks_count": debater_breaks,
            "prelims_debated": prelims_cnt,
            "tournaments_debated": tourneys_cnt,
            "total_debates": tot_debates,
            "total_wins": wins,
            "highest_achievement": person_ach.get(pid, "Preliminary Rounds"),
            "position_averages": positions,
            "tournament_breakdown": tournament_breakdown,
        }

