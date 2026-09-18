"""
Unit and Integration Tests for MotionAnalytics Engine
"""

import sqlite3
import pytest
from atomos.analytics.motions import MotionAnalytics
from atomos.database.connection import get_connection


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


@pytest.fixture
def engine(conn):
    return MotionAnalytics(conn)


def test_classify_motion_theme():
    # 1. Tech & AI
    assert MotionAnalytics.classify_motion_theme("This house predicts the AI bubble will crash") == "Tech, AI & Science"
    assert MotionAnalytics.classify_motion_theme("American frontier AI firms should cease cooperation") == "Tech, AI & Science"

    # 2. Geopolitics & IR
    assert MotionAnalytics.classify_motion_theme("THW remove permanent membership status from the UN security council") == "Geopolitics & International Relations"
    assert MotionAnalytics.classify_motion_theme("THS the US led military interventions in Venezuela and iran") == "Geopolitics & International Relations"

    # 3. Social, Gender & Identity
    assert MotionAnalytics.classify_motion_theme("THBT the feminist movement should focus on combatting benevolent sexism") == "Social, Gender & Identity"
    assert MotionAnalytics.classify_motion_theme("This house believes that it is in the interest of the LGBTQIA+ movement") == "Social, Gender & Identity"

    # 4. Law, Crime & Justice
    assert MotionAnalytics.classify_motion_theme("This House supports Jury Nullification") == "Law, Crime & Justice"
    assert MotionAnalytics.classify_motion_theme("San Pedro model of incarceration") == "Law, Crime & Justice"

    # 5. Economics & Development
    assert MotionAnalytics.classify_motion_theme("In developing nations, This House would nationalize all public services") == "Economics & Development"
    assert MotionAnalytics.classify_motion_theme("THBT the Sri Lankan government should prioritize subsidizing private tuition") == "Economics & Development"

    # 6. Culture, Media & Sports
    assert MotionAnalytics.classify_motion_theme("As FIFA, regrets choosing USA as the host for the 2026 World Cup") == "Culture, Media & Sports"
    assert MotionAnalytics.classify_motion_theme("THR the rise of franchise sports leagues") == "Culture, Media & Sports"

    # 7. Philosophy, Ethics & Religion
    assert MotionAnalytics.classify_motion_theme("THW REMOVE LUST FROM THE LIST OF SEVEN DEADLY SINS") == "Philosophy, Ethics & Religion"
    assert MotionAnalytics.classify_motion_theme("THP Moral Relativism to Moral Absolutism") == "Philosophy, Ethics & Religion"

    # 8. Environment & Animals
    assert MotionAnalytics.classify_motion_theme("domestication of pets and livestock has done more harm than good") == "Environment & Animals"

    # 9. None or Empty
    assert MotionAnalytics.classify_motion_theme(None) == "General & Policy"
    assert MotionAnalytics.classify_motion_theme("") == "General & Policy"


def test_overall_side_balance(engine):
    balance = engine.get_overall_side_balance()

    assert balance["total_decisions"] > 0
    assert balance["prop_wins"] + balance["opp_wins"] + balance["ties"] == balance["total_decisions"]
    assert balance["prop_win_rate"] + balance["opp_win_rate"] <= 100.1
    assert balance["dominant_side"] in ["Proposition", "Opposition", "Balanced"]
    assert balance["bias_classification"] in ["BALANCED", "SLIGHT_PROP_BIAS", "HEAVILY_PROP_BIASED", "SLIGHT_OPP_BIAS", "HEAVILY_OPP_BIASED"]


def test_tournament_side_balance(engine):
    tourneys = engine.get_tournament_side_balance()
    assert len(tourneys) >= 8

    for t in tourneys:
        assert "tournament_name" in t
        assert "tournament_slug" in t
        assert t["total_decisions"] > 0
        assert t["prop_wins"] + t["opp_wins"] + t["ties"] == t["total_decisions"]
        assert t["dominant_side"] in ["Proposition", "Opposition", "Balanced"]


def test_round_type_side_balance(engine):
    breakdown = engine.get_round_type_side_balance()
    assert "PRELIMINARY" in breakdown
    assert "ELIMINATION" in breakdown

    prelim = breakdown["PRELIMINARY"]
    elim = breakdown["ELIMINATION"]

    assert prelim["total_decisions"] > elim["total_decisions"]
    assert prelim["total_decisions"] > 500
    assert elim["total_decisions"] > 50


def test_motion_balance_report(engine):
    report = engine.get_motion_balance_report(min_debates=2)
    assert len(report) >= 40

    for m in report:
        assert "motion" in m
        assert "theme" in m
        assert "tournament_slug" in m
        assert m["debates_count"] >= 2
        assert m["prop_win_rate"] >= 0.0
        assert m["opp_win_rate"] >= 0.0
        assert m["bias_classification"] in ["BALANCED", "SLIGHT_PROP_BIAS", "HEAVILY_PROP_BIASED", "SLIGHT_OPP_BIAS", "HEAVILY_OPP_BIASED"]


def test_thematic_motion_analysis(engine):
    themes = engine.get_thematic_motion_analysis()
    assert len(themes) >= 6

    total_decisions = sum(th["decisions_count"] for th in themes)
    assert total_decisions > 700

    for th in themes:
        assert "theme" in th
        assert th["motions_count"] >= 1
        assert th["decisions_count"] >= 1
        assert th["prop_win_rate"] + th["opp_win_rate"] <= 100.1
        assert th["avg_team_score"] > 0.0


def test_motion_difficulty_ranking(engine):
    toughest = engine.get_motion_difficulty_ranking(min_debates=3, reverse=False)
    highest = engine.get_motion_difficulty_ranking(min_debates=3, reverse=True)

    assert len(toughest) > 0
    assert len(highest) > 0
    assert toughest[0]["avg_team_score"] <= highest[0]["avg_team_score"]


def test_extreme_motions(engine):
    extremes = engine.get_extreme_motions(min_debates=4)

    assert "most_prop_biased" in extremes
    assert "most_opp_biased" in extremes
    assert "most_balanced" in extremes

    if extremes["most_prop_biased"]:
        assert extremes["most_prop_biased"][0]["prop_win_rate"] >= 55.0
    if extremes["most_opp_biased"]:
        assert extremes["most_opp_biased"][0]["opp_win_rate"] >= 55.0
    if extremes["most_balanced"]:
        assert abs(extremes["most_balanced"][0]["prop_win_rate"] - 50.0) <= 10.0
