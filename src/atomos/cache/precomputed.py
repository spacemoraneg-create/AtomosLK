"""
Atomos Precomputed Cache Engine

Provides high-speed caching for heavy analytical aggregations (Master Tab, Critical Stats, IPI).
Enables sub-10ms response times for high-concurrency web deployments.
"""

import json
import sqlite3
from typing import Any, Dict, List, Optional

from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.judges import JudgeAnalyticsEngine
from atomos.analytics.activity import ActivityLeaderboardEngine
from atomos.analytics.tournaments import TournamentRankingsEngine


class PrecomputedCache:
    """Manages materialized JSON caches in atomos.db for lightning-fast frontend delivery."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS precomputed_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def set(self, key: str, data: Any):
        payload = json.dumps(data)
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO precomputed_cache (cache_key, payload_json, item_count, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                item_count = excluded.item_count,
                updated_at = CURRENT_TIMESTAMP
        """, (key, payload, count))
        self.conn.commit()

    def get(self, key: str) -> Optional[Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT payload_json FROM precomputed_cache WHERE cache_key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["payload_json"])

    def refresh_all(self) -> Dict[str, int]:
        """Precomputes all circuit-wide tables and materializes into cache."""
        cur = self.conn.cursor()

        # 1. Master Tab
        mt_engine = MasterTabEngine(self.conn)
        mtab = mt_engine.get_master_speaker_tab(min_tournaments=1)
        self.set("master_speaker_tab", mtab)

        # 2. Master Reply Tab
        rtab = mt_engine.get_master_reply_tab(min_speeches=1)
        self.set("master_reply_tab", rtab)

        # 3. Critical Stats
        c_engine = CriticalStatsEngine(self.conn)
        cstats = c_engine.get_critical_speaker_stats(min_tournaments=3)
        self.set("critical_speaker_stats", cstats)

        # 4. Team Leaderboards (Team Tab: min 3 tournaments debated)
        mteams = c_engine.get_critical_team_stats(min_tournaments=3)
        self.set("master_team_tab", mteams)
        self.set("critical_team_stats", mteams)

        # 5. Institution Leaderboard (Institutional Delta)
        i_engine = InstitutionAnalytics(self.conn)
        ipi = i_engine.get_institutional_delta_leaderboard()
        self.set("institutional_power_index", ipi)

        # 6. Judges Leaderboard
        j_engine = JudgeAnalyticsEngine(self.conn)
        judges = j_engine.get_judge_leaderboard(min_debates=2)
        self.set("judge_leaderboard", judges)

        # 6b. Activity Leaderboard
        act_engine = ActivityLeaderboardEngine(self.conn)
        act_lb = act_engine.get_activity_leaderboard()
        self.set("activity_leaderboard", act_lb)

        # 6c. Tournament Rankings
        t_engine = TournamentRankingsEngine(self.conn)
        t_rankings = t_engine.get_tournament_rankings()
        self.set("tournament_rankings", t_rankings)

        # 7. National Contingent Roster
        cur.execute("""
            SELECT p.id, p.canonical_name, p.national_level,
                   COALESCE(i.name, 'Independent') as institution,
                   COALESCE(i.name, 'Independent') as institution_name
            FROM persons p
            LEFT JOIN (
                SELECT tm.person_id, t.institution_id
                FROM team_members tm
                JOIN teams t ON tm.team_id = t.id
                GROUP BY tm.person_id
            ) primary_inst ON p.id = primary_inst.person_id
            LEFT JOIN institutions i ON primary_inst.institution_id = i.id
            WHERE p.national_level IS NOT NULL
            ORDER BY p.national_level, p.canonical_name
        """)
        nat_rows = [dict(r) for r in cur.fetchall()]
        self.set("national_pool", nat_rows)

        # 8. Lightweight Search Index
        cur.execute("SELECT id, canonical_name FROM persons ORDER BY canonical_name")
        persons_idx = [{"id": r["id"], "name": r["canonical_name"], "type": "debater"} for r in cur.fetchall()]

        cur.execute("SELECT id, name, code FROM institutions ORDER BY name")
        inst_idx = [{"id": r["id"], "name": r["name"], "code": r["code"], "type": "institution"} for r in cur.fetchall()]

        cur.execute("SELECT id, name, slug FROM tournaments ORDER BY id")
        tour_idx = [{"id": r["id"], "name": r["name"], "slug": r["slug"], "type": "tournament"} for r in cur.fetchall()]

        search_index = {
            "debaters": persons_idx,
            "institutions": inst_idx,
            "tournaments": tour_idx,
        }
        self.set("search_index", search_index)

        # 9. V2 Analytical Materializations
        from atomos.analytics.v2_metrics import V2MetricsEngine
        v2 = V2MetricsEngine(self.conn)

        v2_speakers_tab = v2.get_multipurpose_speakers(tier="tab", sort_by="speaker_score")
        self.set("v2_speakers_tab", v2_speakers_tab)

        v2_speakers_general = v2.get_multipurpose_speakers(tier="general", sort_by="speaker_score")
        self.set("v2_speakers_general", v2_speakers_general)

        v2_teams_tab = v2.get_multipurpose_teams(tier="tab", sort_by="atss")
        self.set("v2_teams_tab", v2_teams_tab)

        v2_teams_general = v2.get_multipurpose_teams(tier="general", sort_by="atss")
        self.set("v2_teams_general", v2_teams_general)

        v2_institutions_tab = v2.get_multipurpose_institutions(tier="tab", sort_by="delta")
        self.set("v2_institutions_tab", v2_institutions_tab)

        v2_institutions_general = v2.get_multipurpose_institutions(tier="general", sort_by="delta")
        self.set("v2_institutions_general", v2_institutions_general)

        v2_tournaments = v2.get_tournament_hard_rankings()
        self.set("v2_tournaments", v2_tournaments)

        v2_adjudicators = v2.get_adjudicator_leaderboard()
        self.set("v2_adjudicators", v2_adjudicators)

        v2_national_pool = v2.get_national_pool_tiers()
        self.set("v2_national_pool", v2_national_pool)

        return {
            "master_speaker_tab": len(mtab),
            "master_reply_tab": len(rtab),
            "critical_speaker_stats": len(cstats),
            "master_team_tab": len(mteams),
            "critical_team_stats": len(mteams),
            "institutional_power_index": len(ipi),
            "judge_leaderboard": len(judges),
            "national_pool": len(nat_rows),
            "search_index_entries": len(persons_idx) + len(inst_idx) + len(tour_idx),
            "v2_speakers_tab": len(v2_speakers_tab),
            "v2_speakers_general": len(v2_speakers_general),
            "v2_teams_tab": len(v2_teams_tab),
            "v2_teams_general": len(v2_teams_general),
            "v2_institutions_tab": len(v2_institutions_tab),
            "v2_institutions_general": len(v2_institutions_general),
            "v2_tournaments": len(v2_tournaments),
            "v2_adjudicators": len(v2_adjudicators),
            "v2_national_pool": v2_national_pool.get("total_count", 0),
        }

