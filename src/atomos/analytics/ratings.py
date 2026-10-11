"""
Atomos Debating Elo and Rating Engine

Features:
1. International Standard 3-Tier Elo Rating System (Debaters, Teams, Institutions)
   - Base rating R_0 = 1500.0
   - Logistic expected score E_A = 1 / (1 + 10^((R_B - R_A) / 400))
   - FIDE / International dynamic K-factor scaling by experience & stage
   - Strictly chronological across tournaments and rounds
2. Legacy WSDC Margin-Weighted Team Elo & Debater Performance Index (DPI)
"""

from collections import defaultdict
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from atomos.analytics.tournaments import CHRONOLOGICAL_TOURNAMENT_ORDER, CLEAN_TOURNAMENT_NAMES
from atomos.analytics.v2_metrics import CANONICAL_TEAM_ALIASES, truncate_3



def _is_excluded_team(name: Optional[str]) -> bool:
    if not name:
        return True
    low = name.lower()
    return "swing" in low or "bye" in low or "composite" in low


def _is_excluded_institution(name: Optional[str]) -> bool:
    if not name:
        return True
    low = name.lower()
    return "swing" in low or "independent" in low or "composite" in low


class EloRatingEngine:
    """Computes international standard Elo ratings across Debaters, Teams, and Institutions."""

    DEFAULT_INITIAL_RATING = 1500.0
    DEFAULT_PRELIM_K = 32.0
    DEFAULT_ELIM_K = 48.0

    def __init__(
        self,
        conn: sqlite3.Connection,
        initial_rating: float = DEFAULT_INITIAL_RATING,
        prelim_k: float = DEFAULT_PRELIM_K,
        elim_k: float = DEFAULT_ELIM_K,
    ):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.initial_rating = initial_rating
        self.prelim_k = prelim_k
        self.elim_k = elim_k

    def calculate_margin_multiplier(self, margin: float) -> float:
        """
        Computes margin multiplier M = ln(1 + |margin|).
        Constrained between 1.0 and 3.0 for stability.
        """
        raw_m = math.log(1.0 + abs(margin))
        return max(1.0, min(3.0, raw_m))

    def calculate_expected_score(self, rating_a: float, rating_b: float) -> float:
        """International standard logistic expected score formula (base 10, scale 400)."""
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def get_international_k_factor(
        self,
        rating: float,
        matches_played: int,
        round_type: str,
        entity_type: str = "debater",
    ) -> float:
        """
        International standard (FIDE-style) dynamic K-factor:
        - Provisional / new entities adjust faster (K=40)
        - Standard established entities use K=32 (prelims) / K=40 (eliminations)
        - High-rated established entities (>= 1675) stabilize with K=24 (prelims) / K=32 (eliminations)
        - Institutions field multiple teams per round, so K is scaled appropriately (20 prelim / 28 elim).
        """
        is_elim = round_type == "ELIMINATION"
        if entity_type == "institution":
            if matches_played < 18:
                return 28.0 if is_elim else 24.0
            if rating >= 1675.0:
                return 22.0 if is_elim else 16.0
            return 28.0 if is_elim else 20.0

        # Debater and Team international standard K-factors
        if matches_played < 12:
            return 44.0 if is_elim else 40.0
        if rating >= 1675.0:
            return 32.0 if is_elim else 24.0
        return 40.0 if is_elim else 32.0

    def compute_all_international_elos(self) -> Dict[str, Dict[Any, Dict[str, Any]]]:
        """
        Simulates all contested circuit debates in strict chronological order and computes
        3 distinct International Standard Elo ratings:
        1. 'debaters': keyed by person_id (int)
        2. 'teams': keyed by canonical team_name (str)
        3. 'institutions': keyed by institution_id (int) and institution_name (str)
        """
        cur = self.conn.cursor()

        # 1. Fetch all contested debates with panel-aggregated ballot decisions
        cur.execute("""
            SELECT d.id as debate_id,
                   d.is_walkover,
                   r.tournament_id,
                   t.name as tournament_name,
                   r.round_number,
                   r.name as round_name,
                   r.round_type,
                   d.prop_team_id,
                   d.opp_team_id,
                   pt.name as prop_raw_name,
                   ot.name as opp_raw_name,
                   pt.institution_id as prop_inst_id,
                   inst_p.name as prop_inst_name,
                   ot.institution_id as opp_inst_id,
                   inst_o.name as opp_inst_name,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_votes,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_votes,
                   SUM(CASE WHEN b.winner_side = 'Tie' THEN 1 ELSE 0 END) as tie_votes
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions inst_p ON pt.institution_id = inst_p.id
            LEFT JOIN institutions inst_o ON ot.institution_id = inst_o.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0
            GROUP BY d.id
        """)
        raw_debates = cur.fetchall()

        # Sort debates strictly by chronological tournament order, then round_number, then debate_id
        debates = sorted(
            raw_debates,
            key=lambda row: (
                CHRONOLOGICAL_TOURNAMENT_ORDER.get(row["tournament_id"], 999),
                row["round_number"] or 0,
                row["debate_id"],
            ),
        )

        # 2. Pre-fetch substantive speaker performances per (debate_id, team_id)
        #    Averaging across panel ballots and taking max substantive score per speaker in the debate (Iron Man)
        cur.execute("""
            SELECT sp.debate_id,
                   sp.team_id,
                   sp.person_id,
                   p.canonical_name as speaker_name,
                   r.tournament_id,
                   AVG(sp.total_score) as avg_score
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            JOIN rounds r ON sp.round_id = r.id
            JOIN persons p ON sp.person_id = p.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND d.is_walkover = 0
              AND sp.person_id IS NOT NULL
            GROUP BY sp.debate_id, sp.team_id, sp.person_id, sp.position
        """)
        debate_team_speakers: Dict[Tuple[int, int], Dict[int, float]] = defaultdict(dict)
        tournament_team_speaker_counts: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        person_names: Dict[int, str] = {}

        for row in cur.fetchall():
            did = row["debate_id"]
            tid = row["team_id"]
            pid = row["person_id"]
            score = float(row["avg_score"] or 0.0)
            person_names[pid] = row["speaker_name"]
            prev = debate_team_speakers[(did, tid)].get(pid, 0.0)
            if score > prev:
                debate_team_speakers[(did, tid)][pid] = score
            tournament_team_speaker_counts[tid][pid] += 1

        # Pre-fetch team_members as fallback for elimination rounds without speech rows
        cur.execute("""
            SELECT tm.team_id, tm.person_id, p.canonical_name as speaker_name
            FROM team_members tm
            JOIN persons p ON tm.person_id = p.id
        """)
        team_roster_fallback: Dict[int, List[int]] = defaultdict(list)
        for row in cur.fetchall():
            pid = row["person_id"]
            person_names[pid] = row["speaker_name"]
            if pid not in team_roster_fallback[row["team_id"]]:
                team_roster_fallback[row["team_id"]].append(pid)

        def get_active_speakers_for_debate(debate_id: int, team_id: int) -> Tuple[List[int], Dict[int, float]]:
            spk_map = debate_team_speakers.get((debate_id, team_id))
            if spk_map:
                return list(spk_map.keys()), spk_map
            # Fallback for elimination debates where individual speech scores are not on the ballot:
            # use the top 3 primary substantive speakers for this team instance in this tournament
            freq_map = tournament_team_speaker_counts.get(team_id)
            if freq_map:
                top_pids = sorted(freq_map.keys(), key=lambda p: (-freq_map[p], p))[:3]
                return top_pids, {}
            roster = team_roster_fallback.get(team_id, [])[:3]
            return roster, {}

        # State dictionaries for the 3 distinct Elos
        debater_elos: Dict[int, Dict[str, Any]] = {}
        team_elos: Dict[str, Dict[str, Any]] = {}
        institution_elos: Dict[int, Dict[str, Any]] = {}
        institution_elos_by_name: Dict[str, Dict[str, Any]] = {}

        def ensure_debater(pid: int) -> Dict[str, Any]:
            if pid not in debater_elos:
                debater_elos[pid] = {
                    "person_id": pid,
                    "name": person_names.get(pid, f"Debater #{pid}"),
                    "elo": self.initial_rating,
                    "peak_elo": self.initial_rating,
                    "lowest_elo": self.initial_rating,
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "history": [],
                }
            return debater_elos[pid]

        def ensure_team(cname: str, inst_name: str) -> Dict[str, Any]:
            if cname not in team_elos:
                team_elos[cname] = {
                    "team_name": cname,
                    "institution": inst_name or "Independent",
                    "elo": self.initial_rating,
                    "peak_elo": self.initial_rating,
                    "lowest_elo": self.initial_rating,
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "history": [],
                }
            return team_elos[cname]

        def ensure_institution(inst_id: int, inst_name: str) -> Dict[str, Any]:
            if inst_id not in institution_elos:
                rec = {
                    "institution_id": inst_id,
                    "institution_name": inst_name,
                    "elo": self.initial_rating,
                    "peak_elo": self.initial_rating,
                    "lowest_elo": self.initial_rating,
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "history": [],
                }
                institution_elos[inst_id] = rec
                institution_elos_by_name[inst_name.lower()] = rec
            return institution_elos[inst_id]

        # 3. Simulate all debates chronologically
        for d in debates:
            did = d["debate_id"]
            rtype = d["round_type"] or "PRELIMINARY"
            p_raw = d["prop_raw_name"] or ""
            o_raw = d["opp_raw_name"] or ""

            if _is_excluded_team(p_raw) or _is_excluded_team(o_raw):
                continue

            p_votes = d["prop_votes"] or 0
            o_votes = d["opp_votes"] or 0
            t_votes = d["tie_votes"] or 0

            if p_votes == 0 and o_votes == 0 and t_votes == 0:
                continue

            if p_votes > o_votes:
                s_prop, s_opp = 1.0, 0.0
            elif o_votes > p_votes:
                s_prop, s_opp = 0.0, 1.0
            else:
                s_prop, s_opp = 0.5, 0.5

            p_cname = CANONICAL_TEAM_ALIASES.get(p_raw, p_raw)
            o_cname = CANONICAL_TEAM_ALIASES.get(o_raw, o_raw)
            p_inst_name = d["prop_inst_name"] or "Independent"
            o_inst_name = d["opp_inst_name"] or "Independent"
            p_inst_id = d["prop_inst_id"]
            o_inst_id = d["opp_inst_id"]

            # -----------------------------------------------------------------
            # A. TEAM ELO UPDATE (Canonical Teams)
            # -----------------------------------------------------------------
            if p_cname != o_cname:
                t_prop = ensure_team(p_cname, p_inst_name)
                t_opp = ensure_team(o_cname, o_inst_name)

                r_tp = t_prop["elo"]
                r_to = t_opp["elo"]

                e_tp = self.calculate_expected_score(r_tp, r_to)
                e_to = 1.0 - e_tp

                k_tp = self.get_international_k_factor(r_tp, t_prop["matches_played"], rtype, "team")
                k_to = self.get_international_k_factor(r_to, t_opp["matches_played"], rtype, "team")

                new_tp = r_tp + k_tp * (s_prop - e_tp)
                new_to = r_to + k_to * (s_opp - e_to)

                t_prop["elo"] = new_tp
                t_prop["peak_elo"] = max(t_prop["peak_elo"], new_tp)
                t_prop["lowest_elo"] = min(t_prop["lowest_elo"], new_tp)
                t_prop["matches_played"] += 1
                if s_prop == 1.0:
                    t_prop["wins"] += 1
                elif s_prop == 0.0:
                    t_prop["losses"] += 1

                t_opp["elo"] = new_to
                t_opp["peak_elo"] = max(t_opp["peak_elo"], new_to)
                t_opp["lowest_elo"] = min(t_opp["lowest_elo"], new_to)
                t_opp["matches_played"] += 1
                if s_opp == 1.0:
                    t_opp["wins"] += 1
                elif s_opp == 0.0:
                    t_opp["losses"] += 1

            # -----------------------------------------------------------------
            # B. INSTITUTION ELO UPDATE (Inter-School Contested Clashes)
            # -----------------------------------------------------------------
            if (
                p_inst_id
                and o_inst_id
                and p_inst_id != o_inst_id
                and not _is_excluded_institution(p_inst_name)
                and not _is_excluded_institution(o_inst_name)
            ):
                i_prop = ensure_institution(p_inst_id, p_inst_name)
                i_opp = ensure_institution(o_inst_id, o_inst_name)

                r_ip = i_prop["elo"]
                r_io = i_opp["elo"]

                e_ip = self.calculate_expected_score(r_ip, r_io)
                e_io = 1.0 - e_ip

                k_ip = self.get_international_k_factor(r_ip, i_prop["matches_played"], rtype, "institution")
                k_io = self.get_international_k_factor(r_io, i_opp["matches_played"], rtype, "institution")

                new_ip = r_ip + k_ip * (s_prop - e_ip)
                new_io = r_io + k_io * (s_opp - e_io)

                i_prop["elo"] = new_ip
                i_prop["peak_elo"] = max(i_prop["peak_elo"], new_ip)
                i_prop["lowest_elo"] = min(i_prop["lowest_elo"], new_ip)
                i_prop["matches_played"] += 1
                if s_prop == 1.0:
                    i_prop["wins"] += 1
                elif s_prop == 0.0:
                    i_prop["losses"] += 1

                i_opp["elo"] = new_io
                i_opp["peak_elo"] = max(i_opp["peak_elo"], new_io)
                i_opp["lowest_elo"] = min(i_opp["lowest_elo"], new_io)
                i_opp["matches_played"] += 1
                if s_opp == 1.0:
                    i_opp["wins"] += 1
                elif s_opp == 0.0:
                    i_opp["losses"] += 1

            # -----------------------------------------------------------------
            # C. DEBATER ELO UPDATE (Individual Lineup + Pairwise Speaker Score)
            # -----------------------------------------------------------------
            p_pids, p_scores = get_active_speakers_for_debate(did, d["prop_team_id"])
            o_pids, o_scores = get_active_speakers_for_debate(did, d["opp_team_id"])

            if p_pids and o_pids:
                p_records = [ensure_debater(pid) for pid in p_pids]
                o_records = [ensure_debater(pid) for pid in o_pids]

                avg_r_prop = sum(rec["elo"] for rec in p_records) / len(p_records)
                avg_r_opp = sum(rec["elo"] for rec in o_records) / len(o_records)

                has_valid_scores = (
                    len(p_scores) > 0
                    and len(o_scores) > 0
                    and all(sc > 0 for sc in p_scores.values())
                    and all(sc > 0 for sc in o_scores.values())
                )

                # Compute new ratings before mutating so all speakers in the room see pre-match ratings
                p_new_ratings = []
                for rec in p_records:
                    pid = rec["person_id"]
                    r_i = rec["elo"]
                    e_i = self.calculate_expected_score(r_i, avg_r_opp)
                    k_i = self.get_international_k_factor(r_i, rec["matches_played"], rtype, "debater")

                    if has_valid_scores and pid in p_scores:
                        my_sc = p_scores[pid]
                        opp_sc_list = list(o_scores.values())
                        indiv_pts = sum(
                            1.0 if my_sc > osc else (0.5 if my_sc == osc else 0.0)
                            for osc in opp_sc_list
                        ) / len(opp_sc_list)
                        s_eff = 0.80 * s_prop + 0.20 * indiv_pts
                    else:
                        s_eff = s_prop

                    new_r = r_i + k_i * (s_eff - e_i)
                    p_new_ratings.append((rec, new_r, r_i, e_i, s_eff, k_i, avg_r_opp, s_prop, p_scores.get(pid), o_raw, "Proposition"))

                o_new_ratings = []
                for rec in o_records:
                    pid = rec["person_id"]
                    r_j = rec["elo"]
                    e_j = self.calculate_expected_score(r_j, avg_r_prop)
                    k_j = self.get_international_k_factor(r_j, rec["matches_played"], rtype, "debater")

                    if has_valid_scores and pid in o_scores:
                        my_sc = o_scores[pid]
                        prop_sc_list = list(p_scores.values())
                        indiv_pts = sum(
                            1.0 if my_sc > psc else (0.5 if my_sc == psc else 0.0)
                            for psc in prop_sc_list
                        ) / len(prop_sc_list)
                        s_eff = 0.80 * s_opp + 0.20 * indiv_pts
                    else:
                        s_eff = s_opp

                    new_r = r_j + k_j * (s_eff - e_j)
                    o_new_ratings.append((rec, new_r, r_j, e_j, s_eff, k_j, avg_r_prop, s_opp, o_scores.get(pid), p_raw, "Opposition"))

                for rec, new_r, old_r, e_val, s_eff, k_val, opp_avg, team_win, my_sc, opp_name, side in p_new_ratings:
                    rec["history"].append({
                        "debate_id": did,
                        "tournament_id": d["tournament_id"],
                        "tournament_name": CLEAN_TOURNAMENT_NAMES.get(d["tournament_id"], d["tournament_name"]),
                        "round_number": d["round_number"],
                        "round_name": d["round_name"],
                        "round_type": rtype,
                        "team": p_raw,
                        "opponent_team": opp_name,
                        "side": side,
                        "won": team_win == 1.0,
                        "speaker_score": my_sc,
                        "rating_before": truncate_3(old_r),
                        "rating_after": truncate_3(new_r),
                        "delta": truncate_3(new_r - old_r),
                        "opp_avg_elo": truncate_3(opp_avg),
                        "k_factor": k_val,
                    })
                    rec["elo"] = new_r
                    rec["peak_elo"] = max(rec["peak_elo"], new_r)
                    rec["lowest_elo"] = min(rec["lowest_elo"], new_r)
                    rec["matches_played"] += 1
                    if s_prop == 1.0:
                        rec["wins"] += 1
                    elif s_prop == 0.0:
                        rec["losses"] += 1

                for rec, new_r, old_r, e_val, s_eff, k_val, opp_avg, team_win, my_sc, opp_name, side in o_new_ratings:
                    rec["history"].append({
                        "debate_id": did,
                        "tournament_id": d["tournament_id"],
                        "tournament_name": CLEAN_TOURNAMENT_NAMES.get(d["tournament_id"], d["tournament_name"]),
                        "round_number": d["round_number"],
                        "round_name": d["round_name"],
                        "round_type": rtype,
                        "team": o_raw,
                        "opponent_team": opp_name,
                        "side": side,
                        "won": team_win == 1.0,
                        "speaker_score": my_sc,
                        "rating_before": truncate_3(old_r),
                        "rating_after": truncate_3(new_r),
                        "delta": truncate_3(new_r - old_r),
                        "opp_avg_elo": truncate_3(opp_avg),
                        "k_factor": k_val,
                    })
                    rec["elo"] = new_r
                    rec["peak_elo"] = max(rec["peak_elo"], new_r)
                    rec["lowest_elo"] = min(rec["lowest_elo"], new_r)
                    rec["matches_played"] += 1
                    if s_opp == 1.0:
                        rec["wins"] += 1
                    elif s_opp == 0.0:
                        rec["losses"] += 1


        # Truncate to max 3 decimals (Atomos universal formatting rule)
        for rec in debater_elos.values():
            rec["elo"] = truncate_3(rec["elo"])
            rec["peak_elo"] = truncate_3(rec["peak_elo"])
            rec["lowest_elo"] = truncate_3(rec["lowest_elo"])

        for rec in team_elos.values():
            rec["elo"] = truncate_3(rec["elo"])
            rec["peak_elo"] = truncate_3(rec["peak_elo"])
            rec["lowest_elo"] = truncate_3(rec["lowest_elo"])

        for rec in institution_elos.values():
            rec["elo"] = truncate_3(rec["elo"])
            rec["peak_elo"] = truncate_3(rec["peak_elo"])
            rec["lowest_elo"] = truncate_3(rec["lowest_elo"])

        return {
            "debaters": debater_elos,
            "teams": team_elos,
            "institutions": institution_elos,
            "institutions_by_name": institution_elos_by_name,
        }

    def compute_team_ratings(self) -> Dict[str, dict]:
        """
        Simulates all debates chronologically and returns updated Elo ratings per team.
        Preserved for backwards compatibility with MatchPredictor and legacy callers.
        """
        cur = self.conn.cursor()

        cur.execute("""
            SELECT d.id as debate_id, d.is_walkover,
                   t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug,
                   r.round_number, r.round_type,
                   pt.name as prop_name,
                   ot.name as opp_name,
                   inst_p.name as prop_institution,
                   inst_o.name as opp_institution,
                   AVG(b.prop_total_score) as prop_total_score,
                   AVG(b.opp_total_score) as opp_total_score,
                   AVG(b.win_margin) as win_margin,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_votes,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_votes
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions inst_p ON pt.institution_id = inst_p.id
            LEFT JOIN institutions inst_o ON ot.institution_id = inst_o.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0
            GROUP BY d.id
        """)
        raw_debates = cur.fetchall()
        debates = sorted(
            raw_debates,
            key=lambda row: (
                CHRONOLOGICAL_TOURNAMENT_ORDER.get(row["tournament_id"], 999),
                row["round_number"] or 0,
                row["debate_id"],
            ),
        )

        ratings: Dict[str, dict] = {}

        def get_team_record(team_name: str, inst_name: str) -> dict:
            if team_name not in ratings:
                ratings[team_name] = {
                    "team_name": team_name,
                    "institution": inst_name or "Independent",
                    "rating": self.initial_rating,
                    "peak_rating": self.initial_rating,
                    "lowest_rating": self.initial_rating,
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "history": [],
                }
            return ratings[team_name]

        for d in debates:
            p_raw = d["prop_name"]
            o_raw = d["opp_name"]

            if _is_excluded_team(p_raw) or _is_excluded_team(o_raw):
                continue

            p_name = CANONICAL_TEAM_ALIASES.get(p_raw, p_raw)
            o_name = CANONICAL_TEAM_ALIASES.get(o_raw, o_raw)
            if p_name == o_name:
                continue

            p_votes = d["prop_votes"] or 0
            o_votes = d["opp_votes"] or 0
            if p_votes == 0 and o_votes == 0:
                continue

            prop_rec = get_team_record(p_name, d["prop_institution"])
            opp_rec = get_team_record(o_name, d["opp_institution"])

            r_prop = prop_rec["rating"]
            r_opp = opp_rec["rating"]

            e_prop = self.calculate_expected_score(r_prop, r_opp)
            e_opp = 1.0 - e_prop

            if p_votes > o_votes:
                s_prop, s_opp = 1.0, 0.0
                prop_rec["wins"] += 1
                opp_rec["losses"] += 1
            elif o_votes > p_votes:
                s_prop, s_opp = 0.0, 1.0
                prop_rec["losses"] += 1
                opp_rec["wins"] += 1
            else:
                s_prop, s_opp = 0.5, 0.5

            k_prop = self.get_international_k_factor(r_prop, prop_rec["matches_played"], d["round_type"], "team")
            k_opp = self.get_international_k_factor(r_opp, opp_rec["matches_played"], d["round_type"], "team")

            delta_prop = k_prop * (s_prop - e_prop)
            delta_opp = k_opp * (s_opp - e_opp)

            new_r_prop = round(r_prop + delta_prop, 5)
            new_r_opp = round(r_opp + delta_opp, 5)

            prop_rec["rating"] = new_r_prop
            prop_rec["peak_rating"] = max(prop_rec["peak_rating"], new_r_prop)
            prop_rec["lowest_rating"] = min(prop_rec["lowest_rating"], new_r_prop)
            prop_rec["matches_played"] += 1
            prop_rec["history"].append({
                "debate_id": d["debate_id"],
                "opponent": o_name,
                "result": "WIN" if s_prop == 1.0 else "LOSS" if s_prop == 0.0 else "TIE",
                "delta": round(delta_prop, 5),
                "rating_after": new_r_prop,
            })

            opp_rec["rating"] = new_r_opp
            opp_rec["peak_rating"] = max(opp_rec["peak_rating"], new_r_opp)
            opp_rec["lowest_rating"] = min(opp_rec["lowest_rating"], new_r_opp)
            opp_rec["matches_played"] += 1
            opp_rec["history"].append({
                "debate_id": d["debate_id"],
                "opponent": p_name,
                "result": "WIN" if s_opp == 1.0 else "LOSS" if s_opp == 0.0 else "TIE",
                "delta": round(delta_opp, 5),
                "rating_after": new_r_opp,
            })

        return ratings

    def get_ranked_teams(self, min_matches: int = 3) -> List[dict]:
        """Returns sorted Elo leaderboard."""
        ratings = self.compute_team_ratings()
        filtered = [t for t in ratings.values() if t["matches_played"] >= min_matches]
        filtered.sort(key=lambda x: (x["rating"], x["wins"]), reverse=True)

        for rank, entry in enumerate(filtered, start=1):
            entry["rank"] = rank
        return filtered

    def get_debater_performance_index(self, min_speeches: int = 3) -> List[dict]:
        """
        Calculates Debater Performance Index (DPI).
        Measures individual score relative to the position benchmark (1st, 2nd, 3rd)
        within each tournament.
        """
        cur = self.conn.cursor()

        cur.execute("""
            SELECT r.tournament_id, sp.position, AVG(sp.total_score) as avg_benchmark
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY r.tournament_id, sp.position
        """)
        benchmarks = {(row["tournament_id"], row["position"]): row["avg_benchmark"] for row in cur.fetchall()}

        cur.execute("""
            SELECT p.id as person_id, p.canonical_name as speaker_name,
                   p.national_level,
                   inst.name as institution_name,
                   r.tournament_id, sp.position, sp.total_score
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            JOIN teams tm ON sp.team_id = tm.id
            JOIN persons p ON sp.person_id = p.id
            LEFT JOIN institutions inst ON tm.institution_id = inst.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
        """)
        speeches = cur.fetchall()

        person_dpi: Dict[int, List[float]] = {}
        person_meta: Dict[int, dict] = {}

        for sp in speeches:
            pid = sp["person_id"]
            tid = sp["tournament_id"]
            pos = sp["position"]
            score = sp["total_score"]

            if pid not in person_meta:
                person_meta[pid] = {
                    "person_id": pid,
                    "speaker_name": sp["speaker_name"],
                    "institution_name": sp["institution_name"] or "Independent / Composite",
                    "national_level": sp["national_level"],
                }

            bench = benchmarks.get((tid, pos), 70.0)
            diff = score - bench
            person_dpi.setdefault(pid, []).append(diff)

        leaderboard = []
        for pid, diffs in person_dpi.items():
            if len(diffs) < min_speeches:
                continue
            avg_dpi = sum(diffs) / len(diffs)
            leaderboard.append({
                "person_id": pid,
                "speaker_name": person_meta[pid]["speaker_name"],
                "institution_name": person_meta[pid]["institution_name"],
                "national_level": person_meta[pid]["national_level"],
                "dpi": round(avg_dpi, 5),
                "speeches_evaluated": len(diffs),
                "peak_impact": round(max(diffs), 5),
            })

        leaderboard.sort(key=lambda x: (x["dpi"], x["speeches_evaluated"]), reverse=True)
        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard

    def get_debater_elo_history(self, identifier: Any) -> Dict[str, Any]:
        """
        Retrieves the complete tournament-by-tournament and match-by-match Elo history for a debater.
        """
        cur = self.conn.cursor()
        pid = None
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            pid = int(identifier)
        else:
            cur.execute("SELECT id FROM persons WHERE canonical_name LIKE ? ORDER BY LENGTH(canonical_name) ASC LIMIT 1", (f"%{identifier}%",))
            row = cur.fetchone()
            if row:
                pid = row[0]

        if not pid:
            return {"error": f"Debater '{identifier}' not found in database."}

        cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (pid,))
        p_row = cur.fetchone()
        canonical_name = p_row[0] if p_row else f"Debater #{pid}"

        elos = self.compute_all_international_elos()
        deb_rec = elos["debaters"].get(pid)
        if not deb_rec:
            return {
                "person_id": pid,
                "canonical_name": canonical_name,
                "current_elo": 1500.0,
                "peak_elo": 1500.0,
                "lowest_elo": 1500.0,
                "matches_played": 0,
                "wins": 0,
                "losses": 0,
                "tournament_summaries": [],
                "match_history": []
            }

        from collections import defaultdict
        tour_groups = defaultdict(list)
        for m in deb_rec.get("history", []):
            tour_groups[m["tournament_name"]].append(m)

        tournament_summaries = []
        for tname, m_list in tour_groups.items():
            wins = sum(1 for m in m_list if m["won"])
            start_elo = m_list[0]["rating_before"]
            end_elo = m_list[-1]["rating_after"]
            net_delta = round(end_elo - start_elo, 3)
            tournament_summaries.append({
                "tournament_name": tname,
                "debates": len(m_list),
                "record": f"{wins}W - {len(m_list) - wins}L",
                "start_elo": start_elo,
                "end_elo": end_elo,
                "net_delta": net_delta,
            })

        return {
            "person_id": pid,
            "canonical_name": canonical_name,
            "current_elo": deb_rec["elo"],
            "peak_elo": deb_rec["peak_elo"],
            "lowest_elo": deb_rec["lowest_elo"],
            "matches_played": deb_rec["matches_played"],
            "wins": deb_rec["wins"],
            "losses": deb_rec["losses"],
            "tournament_summaries": tournament_summaries,
            "match_history": deb_rec.get("history", []),
        }

