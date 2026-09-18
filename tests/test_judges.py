"""
Tests for Atomos Adjudicator Intelligence Engine
"""

import sqlite3
import pytest
from atomos.database.connection import get_connection
from atomos.analytics.judges import JudgeAnalyticsEngine


@pytest.fixture
def db_conn():
    return get_connection()


def test_judge_dossier_retrieval(db_conn):
    engine = JudgeAnalyticsEngine(db_conn)
    # Test on a known real judge in atomos.db
    dossier = engine.get_judge_dossier("Minithi Hewage")
    assert dossier is not None
    assert "Minithi" in dossier["adjudicator_name"]
    assert dossier["total_debates_judged"] >= 1
    assert "record" in dossier
    assert "prop_win_pct" in dossier["record"]
    assert "scoring_metrics" in dossier
    assert "avg_substantive_score" in dossier["scoring_metrics"]
    assert "strictness_label" in dossier["scoring_metrics"]


def test_judge_leaderboard(db_conn):
    engine = JudgeAnalyticsEngine(db_conn)
    lb = engine.get_judge_leaderboard(min_debates=3, sort_by="debates")
    assert len(lb) > 0
    top = lb[0]
    assert "adjudicator_name" in top
    assert "debates_judged" in top
    assert top["debates_judged"] >= 3
    assert "side_bias" in top
    assert "strictness_label" in top


def test_judge_not_found(db_conn):
    engine = JudgeAnalyticsEngine(db_conn)
    dossier = engine.get_judge_dossier("NonExistentJudge12345")
    assert dossier is None
