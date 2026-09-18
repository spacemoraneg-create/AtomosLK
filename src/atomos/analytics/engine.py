"""
Atomos Analytics Engine Facade

Unified entrypoint for all analytical intelligence, leaderboards, and rating models.
"""

import sqlite3
from typing import Dict, List, Optional

from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.ratings import EloRatingEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.motions import MotionAnalytics
from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.judges import JudgeAnalyticsEngine
from atomos.analytics.brackets import BracketEngine
from atomos.analytics.predictor import MatchPredictor


class AnalyticsEngine:
    """Unified access point for all Atomos analytics."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.master_tabs = MasterTabEngine(conn)
        self.ratings = EloRatingEngine(conn)
        self.institutions = InstitutionAnalytics(conn)
        self.motions = MotionAnalytics(conn)
        self.critical_stats = CriticalStatsEngine(conn)
        self.judges = JudgeAnalyticsEngine(conn)
        self.brackets = BracketEngine(conn)
        self.predictor = MatchPredictor(conn)

    def get_master_speaker_tab(
        self,
        min_tournaments: int = 1,
        regulation: str = "new",
    ) -> List[dict]:
        return self.master_tabs.get_master_speaker_tab(
            min_tournaments=min_tournaments,
            regulation=regulation,
        )

    def get_master_reply_tab(self, min_speeches: int = 1) -> List[dict]:
        return self.master_tabs.get_master_reply_tab(min_speeches=min_speeches)

    def get_master_team_tab(self, min_tournaments: int = 1) -> List[dict]:
        return self.master_tabs.get_master_team_tab(min_tournaments=min_tournaments)

    def get_team_elo_rankings(self, min_matches: int = 3) -> List[dict]:
        return self.ratings.get_ranked_teams(min_matches=min_matches)

    def get_debater_impact_rankings(self, min_speeches: int = 3) -> List[dict]:
        return self.ratings.get_debater_performance_index(min_speeches=min_speeches)

    def get_critical_speaker_stats(
        self,
        min_tournaments: int = 3,
        regulation: str = "new",
    ) -> List[dict]:
        return self.critical_stats.get_critical_speaker_stats(
            min_tournaments=min_tournaments,
            regulation=regulation,
        )

    def get_critical_team_stats(self, min_tournaments: int = 3) -> List[dict]:
        return self.critical_stats.get_critical_team_stats(min_tournaments=min_tournaments)

    def get_institution_rankings(self) -> List[dict]:
        return self.institutions.get_institutional_power_index()

    def get_motion_report(self) -> List[dict]:
        return self.motions.get_motion_balance_report()

    def get_side_balance(self) -> dict:
        return self.motions.get_overall_side_balance()

    def get_tournament_bracket(self, tournament: str) -> Optional[dict]:
        return self.brackets.get_tournament_bracket(tournament)

    def get_judge_dossier(self, identifier) -> Optional[dict]:
        return self.judges.get_judge_dossier(identifier)

    def get_judge_leaderboard(
        self,
        min_debates: int = 3,
        sort_by: str = "debates",
        limit: Optional[int] = None,
    ) -> List[dict]:
        return self.judges.get_judge_leaderboard(min_debates=min_debates, sort_by=sort_by, limit=limit)

    def predict_matchup(self, team_a: str, team_b: str) -> Optional[dict]:
        return self.predictor.predict_matchup(team_a, team_b)

    def get_executive_summary(self) -> dict:
        """Returns key statistical indicators across the debating circuit."""
        cur = self.conn.cursor()

        cur.execute("SELECT COUNT(*) as cnt FROM tournaments")
        tour_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM institutions")
        inst_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM persons")
        person_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM debates WHERE is_walkover = 0")
        debates_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances WHERE total_score > 0")
        speeches_cnt = cur.fetchone()["cnt"]

        cur.execute("SELECT AVG(total_score) as avg_score FROM speech_performances WHERE speech_type = 'SUBSTANTIVE' AND total_score > 0")
        avg_sub = round(cur.fetchone()["avg_score"] or 0.0, 5)

        cur.execute("SELECT AVG(total_score) as avg_score FROM speech_performances WHERE speech_type = 'REPLY' AND total_score > 0")
        avg_rep = round(cur.fetchone()["avg_score"] or 0.0, 5)

        top_speakers = self.get_master_speaker_tab(min_tournaments=1)[:5]
        top_teams = self.get_team_elo_rankings(min_matches=3)[:5]
        top_institutions = self.get_institution_rankings()[:5]
        side_balance = self.get_side_balance()

        return {
            "tournaments_count": tour_cnt,
            "institutions_count": inst_cnt,
            "debater_pool": person_cnt,
            "contested_debates": debates_cnt,
            "recorded_speeches": speeches_cnt,
            "average_substantive_score": avg_sub,
            "average_reply_score": avg_rep,
            "side_balance": side_balance,
            "top_speakers": top_speakers,
            "top_teams": top_teams,
            "top_institutions": top_institutions,
        }
