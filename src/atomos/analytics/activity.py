"""
Atomos Activity Leaderboard Engine

Ranks debaters strictly by preliminary activity:
- Prelims debated (primary ranking metric, no eligibility restrictions)
- Secondary tiebreak: Average Speaker Score (ASS) from prelim speeches
- Debater canonical name
- Latest host institution
- Tournaments debated
"""

import sqlite3
from typing import Any, Dict, List


class ActivityLeaderboardEngine:
    """Computes debater activity rankings across preliminary rounds."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_activity_leaderboard(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()

        # 1. Latest host institution representation for every debater
        cur.execute("""
            SELECT sp.person_id, inst.name as inst_name, tour.id as tour_id, r.round_number
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t ON sp.team_id = t.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE sp.total_score > 0
            ORDER BY tour.id DESC, r.round_number DESC
        """)
        latest_inst = {}
        for row in cur.fetchall():
            pid = row[0]
            if pid not in latest_inst:
                latest_inst[pid] = row[1] or "Independent"

        # 2. Activity metrics: prelims debated, tournaments debated, and ASS
        cur.execute("""
            SELECT p.id as person_id,
                   p.canonical_name,
                   p.national_level,
                   COUNT(DISTINCT r.id) as prelims_debated,
                   COUNT(DISTINCT r.tournament_id) as tournaments_debated,
                   AVG(sp.total_score) as ass
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            JOIN persons p ON sp.person_id = p.id
            WHERE r.round_type = 'PRELIMINARY'
              AND sp.speech_type = 'SUBSTANTIVE'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id
            ORDER BY prelims_debated DESC, ass DESC
        """)
        rows = cur.fetchall()

        leaderboard: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            pid = row[0]
            canonical_name = row[1]
            nat_level = row[2]
            prelims = row[3]
            tournaments = row[4]
            ass = round(row[5], 2) if row[5] is not None else 0.0
            inst = latest_inst.get(pid, "Independent")

            leaderboard.append({
                "rank": idx + 1,
                "person_id": pid,
                "debater_name": canonical_name,
                "institution": inst,
                "national_level": nat_level,
                "prelims_debated": prelims,
                "tournaments_debated": tournaments,
                "ass": ass
            })

        return leaderboard
