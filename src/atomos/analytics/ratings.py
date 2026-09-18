"""
Atomos Debating Elo and Rating Engine

Features:
1. WSDC Margin-Weighted Elo Rating System (K=32 prelims, K=48 eliminations)
2. Debater Performance Index (DPI: position-benchmarked debater impact)
"""

import math
import sqlite3
from typing import Dict, List, Optional, Tuple


class EloRatingEngine:
    """Computes dynamic, margin-weighted Elo ratings for debating teams."""

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
        """Standard logistic expected score formula."""
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def compute_team_ratings(self) -> Dict[str, dict]:
        """
        Simulates all debates chronologically and returns updated Elo ratings per team.
        """
        cur = self.conn.cursor()

        # Query all debates with results in chronological order
        cur.execute("""
            SELECT d.id as debate_id, d.is_walkover,
                   t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug,
                   r.round_number, r.round_type,
                   pt.name as prop_name, ot.name as opp_name,
                   inst_p.name as prop_institution,
                   inst_o.name as opp_institution,
                   b.prop_total_score, b.opp_total_score, b.win_margin, b.winner_side
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions inst_p ON pt.institution_id = inst_p.id
            LEFT JOIN institutions inst_o ON ot.institution_id = inst_o.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0
            ORDER BY t.id, r.round_number, d.id
        """)
        debates = cur.fetchall()

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
            p_name = d["prop_name"]
            o_name = d["opp_name"]

            # Skip BYE / Swing matches
            if "swing" in p_name.lower() or "bye" in p_name.lower() or \
               "swing" in o_name.lower() or "bye" in o_name.lower():
                continue

            # Need a valid decision
            winner = d["winner_side"]
            if not winner or winner not in ["Proposition", "Opposition", "Tie"]:
                continue

            prop_rec = get_team_record(p_name, d["prop_institution"])
            opp_rec = get_team_record(o_name, d["opp_institution"])

            r_prop = prop_rec["rating"]
            r_opp = opp_rec["rating"]

            # Expected scores
            e_prop = self.calculate_expected_score(r_prop, r_opp)
            e_opp = 1.0 - e_prop

            # Actual scores
            if winner == "Proposition":
                s_prop = 1.0
                s_opp = 0.0
                prop_rec["wins"] += 1
                opp_rec["losses"] += 1
            elif winner == "Opposition":
                s_prop = 0.0
                s_opp = 1.0
                prop_rec["losses"] += 1
                opp_rec["wins"] += 1
            else:
                s_prop = 0.5
                s_opp = 0.5

            margin = d["win_margin"] if d["win_margin"] is not None else 1.0
            mult = self.calculate_margin_multiplier(margin)
            k = self.DEFAULT_ELIM_K if d["round_type"] == "ELIMINATION" else self.DEFAULT_PRELIM_K

            delta_prop = k * mult * (s_prop - e_prop)
            delta_opp = -delta_prop

            # Apply updates
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

        # 1. Compute benchmark average per (tournament_id, position)
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

        # 2. Query individual speeches
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
                "dpi": round(avg_dpi, 5),  # Impact points above benchmark
                "speeches_evaluated": len(diffs),
                "peak_impact": round(max(diffs), 5),
            })

        leaderboard.sort(key=lambda x: (x["dpi"], x["speeches_evaluated"]), reverse=True)
        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard
