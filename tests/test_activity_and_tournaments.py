import sqlite3
import pytest
from atomos.database.connection import get_connection
from atomos.analytics.tournaments import TournamentRankingsEngine, OFFICIAL_TOURNAMENT_DATES
from atomos.analytics.activity import ActivityLeaderboardEngine
from atomos.query import AtomosQuery


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


def test_tournament_rankings(conn):
    engine = TournamentRankingsEngine(conn)
    rankings = engine.get_tournament_rankings()

    # Exactly 8 active contested tournaments
    assert len(rankings) == 8

    # Strictly non-increasing APTTSS
    apttss_scores = [r["apttss"] for r in rankings]
    for i in range(len(apttss_scores) - 1):
        assert apttss_scores[i] >= apttss_scores[i + 1]

    # Check rank numbers 1 to 8
    for idx, r in enumerate(rankings):
        assert r["rank"] == idx + 1
        assert r["apttss"] > 235.0
        assert r["apttss_breaking"] >= r["apttss"]
        assert r["dates"] != "TBD"
        assert r["teams_participated"] > 0
        assert r["prelim_rounds"] >= 5
        assert r["speeches_count"] > 0
        assert r["debates_count"] > 0
        assert r["break_structure"] in [
            "Octofinals (Top 16)",
            "Quarterfinals (Top 8)",
            "Partial Octos (Top 12)",
            "Semifinals (Top 4)"
        ]


def test_activity_leaderboard(conn):
    engine = ActivityLeaderboardEngine(conn)
    lb = engine.get_activity_leaderboard()

    assert len(lb) >= 500

    # Ranks strictly 1..N
    assert lb[0]["rank"] == 1
    assert lb[0]["prelims_debated"] >= 30

    # Test sorting invariant: prelims_debated descending, ties broken by ass descending
    for i in range(len(lb) - 1):
        p_curr = lb[i]["prelims_debated"]
        p_next = lb[i + 1]["prelims_debated"]
        assert p_curr >= p_next
        if p_curr == p_next:
            assert lb[i]["ass"] >= lb[i + 1]["ass"]

    # Verify top debater details
    top = lb[0]
    assert "debater_name" in top
    assert "institution" in top
    assert "tournaments_debated" in top
    assert top["tournaments_debated"] >= 5
    assert top["ass"] >= 65.0


def test_query_facade(conn):
    query = AtomosQuery(conn)
    t_rankings = query.get_tournament_rankings()
    act_lb = query.get_activity_leaderboard()

    assert len(t_rankings) == 8
    assert len(act_lb) >= 500
