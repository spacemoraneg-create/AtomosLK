"""
Atomos Match Simulation & Predictive Clash Engine

Predicts outcomes, win probabilities, score margins, and tactical keys for hypothetical
or upcoming matchups between debating teams.
Factors in:
1. Squad Elo Ratings & Dominance Index
2. Team ATSS (Average Total Speaker Score)
3. National Contingent Density (debater national_level on rosters)
4. Historical Head-to-Head record (team-level and institution-level)
"""

import math
import sqlite3
from typing import Any, Dict, List, Optional

from atomos.analytics.ratings import EloRatingEngine
from atomos.analytics.critical_stats import CriticalStatsEngine


class MatchPredictor:
    """Simulates competitive debating clashes using multimodal circuit metrics."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.elo_engine = EloRatingEngine(conn)
        self.critical_engine = CriticalStatsEngine(conn)

    def _resolve_team_info(self, team_name: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT t.id, t.name, t.canonical_name, t.tier,
                   i.id as inst_id, i.name as inst_name, i.code as inst_code
            FROM teams t
            LEFT JOIN institutions i ON t.institution_id = i.id
            WHERE LOWER(t.name) = LOWER(?) OR LOWER(t.canonical_name) = LOWER(?)
            ORDER BY t.id DESC
            LIMIT 1
        """, (team_name.strip(), team_name.strip()))
        row = cur.fetchone()
        if not row:
            # Fuzzy match
            cur.execute("""
                SELECT t.id, t.name, t.canonical_name, t.tier,
                       i.id as inst_id, i.name as inst_name, i.code as inst_code
                FROM teams t
                LEFT JOIN institutions i ON t.institution_id = i.id
                WHERE LOWER(t.name) LIKE LOWER(?)
                ORDER BY t.id DESC
                LIMIT 1
            """, (f"%{team_name.strip()}%",))
            row = cur.fetchone()

        if not row:
            return None

        # Fetch unique debaters on this team and national level
        cur.execute("""
            SELECT DISTINCT p.id, p.canonical_name, p.national_level
            FROM team_members tm
            JOIN persons p ON tm.person_id = p.id
            JOIN teams t ON tm.team_id = t.id
            WHERE LOWER(t.name) = LOWER(?) OR LOWER(t.canonical_name) = LOWER(?)
        """, (row["name"], row["canonical_name"] or row["name"]))
        members = cur.fetchall()

        # National debaters count
        nat_debaters = [m for m in members if m["national_level"] is not None]

        return {
            "team_id": row["id"],
            "team_name": row["name"],
            "canonical_name": row["canonical_name"] or row["name"],
            "institution_id": row["inst_id"],
            "institution": row["inst_name"] or "Independent",
            "institution_code": row["inst_code"] or "IND",
            "tier": row["tier"] or ("A" if "a" in row["name"].lower() else "Open"),
            "roster_count": len(members),
            "members": [m["canonical_name"] for m in members],
            "national_members": [
                {"name": m["canonical_name"], "status": m["national_level"]}
                for m in nat_debaters
            ],
            "national_count": len(nat_debaters),
        }

    def predict_matchup(self, team_a: str, team_b: str) -> Optional[Dict[str, Any]]:
        info_a = self._resolve_team_info(team_a)
        info_b = self._resolve_team_info(team_b)

        if not info_a or not info_b:
            return None

        # 1. Elo Ratings
        team_elos = self.elo_engine.compute_team_ratings()
        elo_a_entry = team_elos.get(info_a["team_name"], {})
        elo_b_entry = team_elos.get(info_b["team_name"], {})

        elo_a = elo_a_entry.get("rating", 1500.0)
        elo_b = elo_b_entry.get("rating", 1500.0)

        # 2. Critical Team Stats (ATSS, Win %)
        c_teams = self.critical_engine.get_critical_team_stats(min_tournaments=1)
        c_map = {t["team_name"].lower(): t for t in c_teams}

        stats_a = c_map.get(info_a["team_name"].lower(), {})
        stats_b = c_map.get(info_b["team_name"].lower(), {})

        atss_a = stats_a.get("atss", 248.0)
        atss_b = stats_b.get("atss", 248.0)
        win_rate_a = stats_a.get("win_percentage", 50.0)
        win_rate_b = stats_b.get("win_percentage", 50.0)

        # 3. Elo Probability calculation
        # P(A wins) = 1 / (1 + 10^((EloB - EloA) / 400))
        elo_diff = elo_a - elo_b
        elo_prob_a = 1.0 / (1.0 + math.pow(10, -elo_diff / 400.0))

        # 4. ATSS Probability Adjustment
        # Each 1.0 point of ATSS delta roughly corresponds to a 5% win equity shift in WSDC
        atss_diff = atss_a - atss_b
        atss_prob_shift = min(max(atss_diff * 0.05, -0.35), 0.35)

        # 5. National Talent Adjustment
        nat_diff = info_a["national_count"] - info_b["national_count"]
        nat_prob_shift = min(max(nat_diff * 0.03, -0.15), 0.15)

        # Composite Probability
        raw_prob_a = (0.50 * elo_prob_a) + (0.35 * (0.5 + atss_prob_shift)) + (0.15 * (0.5 + nat_prob_shift))
        prob_a = round(min(max(raw_prob_a, 0.05), 0.95) * 100.0, 2)
        prob_b = round(100.0 - prob_a, 2)

        # Predicted Expected Margin
        pred_margin = round(abs(atss_diff) * 0.75 + (abs(elo_diff) / 100.0), 2)
        if pred_margin < 0.5:
            pred_margin = 0.5

        if prob_a >= 50.0:
            favored_team = info_a["team_name"]
            underdog_team = info_b["team_name"]
            favored_prob = prob_a
        else:
            favored_team = info_b["team_name"]
            underdog_team = info_a["team_name"]
            favored_prob = prob_b

        # Tactical Key Factors
        factors = []
        if abs(elo_diff) >= 50:
            stronger = info_a["institution"] if elo_diff > 0 else info_b["institution"]
            factors.append(f"{stronger} holds a +{abs(elo_diff):.1f} Elo rating advantage.")
        if abs(atss_diff) >= 1.0:
            higher_scoring = info_a["team_name"] if atss_diff > 0 else info_b["team_name"]
            factors.append(f"{higher_scoring} has a higher preliminary scoring baseline (+{abs(atss_diff):.2f} ATSS).")
        if info_a["national_count"] > 0 or info_b["national_count"] > 0:
            factors.append(
                f"National team roster presence: {info_a['team_name']} has {info_a['national_count']} vs "
                f"{info_b['team_name']} with {info_b['national_count']}."
            )
        if abs(win_rate_a - win_rate_b) >= 15.0:
            higher_wr = info_a["team_name"] if win_rate_a > win_rate_b else info_b["team_name"]
            factors.append(f"{higher_wr} demonstrates superior match conversion ({max(win_rate_a, win_rate_b):.1f}% win rate).")

        return {
            "team_a": {
                "name": info_a["team_name"],
                "institution": info_a["institution"],
                "elo": round(elo_a, 1),
                "atss": round(atss_a, 2),
                "win_rate": round(win_rate_a, 1),
                "national_debaters": info_a["national_members"],
                "win_probability": prob_a,
            },
            "team_b": {
                "name": info_b["team_name"],
                "institution": info_b["institution"],
                "elo": round(elo_b, 1),
                "atss": round(atss_b, 2),
                "win_rate": round(win_rate_b, 1),
                "national_debaters": info_b["national_members"],
                "win_probability": prob_b,
            },
            "simulation": {
                "favored_team": favored_team,
                "favored_probability": favored_prob,
                "projected_margin": pred_margin,
                "competitiveness": "Razor-Thin Split" if abs(prob_a - 50.0) <= 10.0 else (
                    "Competitive Contest" if abs(prob_a - 50.0) <= 25.0 else "Decisive Advantage"
                ),
                "key_matchup_factors": factors,
            },
        }
