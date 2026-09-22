"""
Tests for Atomos Institutional Delta Engine & Updated Leaderboards Rules.
"""

import pytest
from atomos.database.connection import get_connection
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.master_tabs import MasterTabEngine


@pytest.fixture(scope="module")
def conn():
    return get_connection()


def test_institutional_delta_leaderboard(conn):
    engine = InstitutionAnalytics(conn)
    board = engine.get_institutional_delta_leaderboard()

    assert len(board) > 0, "Leaderboard should not be empty"

    # Check Royal College
    rc = next((s for s in board if s["institution_name"] == "Royal College"), None)
    assert rc is not None, "Royal College must exist in delta leaderboard"
    assert rc["rank"] == 1, f"Expected Royal College rank 1, got {rc['rank']}"
    assert rc["delta"] == 249.18
    assert rc["a_atss"] == 251.67
    assert rc["b_atss"] == 250.27
    assert rc["net_diff"] == 1.4
    assert rc["break_percentage"] == 83.3
    assert rc["highest_break"] == "Champion"

    # Check D. S. Senanayake College
    ds = next((s for s in board if "D. S." in s["institution_name"]), None)
    assert ds is not None, "D. S. Senanayake College must exist in delta leaderboard"
    assert ds["delta"] == pytest.approx(246.44, abs=0.05)
    assert ds["a_atss"] == pytest.approx(251.27, abs=0.05)
    assert ds["b_atss"] == 245.25
    assert ds["net_diff"] == pytest.approx(6.02, abs=0.05)
    assert ds["break_percentage"] == 78.6, f"Expected DS break % 78.6, got {ds['break_percentage']}"
    assert ds["highest_break"] == "Champion"

    # Verify rank sequence
    for idx, row in enumerate(board, start=1):
        assert row["rank"] == idx


def test_team_leaderboard_min_3_tournaments(conn):
    crit_engine = CriticalStatsEngine(conn)
    teams = crit_engine.get_critical_team_stats(min_tournaments=3)

    assert len(teams) == 45, f"Expected 45 circuit teams with >= 3 tournaments, got {len(teams)}"

    # All returned teams must have tournaments_debated >= 3
    for t in teams:
        assert t["tournaments_debated"] >= 3
        assert "net_margin" in t
        assert "highest_achievement" in t
        assert "atss" in t


def test_debater_latest_host_institution(conn):
    mt_engine = MasterTabEngine(conn)
    tab = mt_engine.get_master_speaker_tab(min_tournaments=1)

    assert len(tab) > 500

    # Vidath Marasinghe should be D. S. Senanayake College
    vidath = next((d for d in tab if d["speaker_name"] == "Vidath Marasinghe"), None)
    assert vidath is not None
    assert vidath["institution"] == "D. S. Senanayake College"
    assert vidath["speaker_avg"] == pytest.approx(72.74, abs=0.05)
    assert vidath["win_percentage"] == 85.3
    assert vidath["prelims"] == 34
    assert vidath["break_percentage"] == 100.0

    # Kulith Wickramasinghe should be Ananda College
    kulith = next((d for d in tab if d["speaker_name"] == "Kulith Wickramasinghe"), None)
    assert kulith is not None
    assert kulith["institution"] == "Ananda College"
    assert kulith["speaker_avg"] == 73.12
