"""
Tests for Atomos Match Simulation & Predictive Clash Engine
"""

import pytest
from atomos.database.connection import get_connection
from atomos.analytics.predictor import MatchPredictor


@pytest.fixture
def db_conn():
    return get_connection()


def test_predictor_valid_matchup(db_conn):
    predictor = MatchPredictor(db_conn)
    result = predictor.predict_matchup("DS A", "RC A")
    assert result is not None
    assert "team_a" in result
    assert "team_b" in result
    assert "simulation" in result

    # Probabilities sum to 100%
    prob_a = result["team_a"]["win_probability"]
    prob_b = result["team_b"]["win_probability"]
    assert round(prob_a + prob_b, 1) == 100.0

    # Simulation contains projected margin & competitiveness
    sim = result["simulation"]
    assert "favored_team" in sim
    assert sim["favored_team"] in [result["team_a"]["name"], result["team_b"]["name"]]
    assert sim["projected_margin"] > 0
    assert sim["competitiveness"] in ["Razor-Thin Split", "Competitive Contest", "Decisive Advantage"]
    assert isinstance(sim["key_matchup_factors"], list)


def test_predictor_invalid_team(db_conn):
    predictor = MatchPredictor(db_conn)
    result = predictor.predict_matchup("NonExistentTeam99", "RC A")
    assert result is None
