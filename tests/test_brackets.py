"""
Tests for Atomos Tournament Knockout Bracket Engine
"""

import pytest
from atomos.database.connection import get_connection
from atomos.analytics.brackets import BracketEngine


@pytest.fixture
def db_conn():
    return get_connection()


def test_bracket_chaps(db_conn):
    engine = BracketEngine(db_conn)
    bracket = engine.get_tournament_bracket("Chaps2026")
    assert bracket is not None
    assert "Chap" in bracket["tournament_name"]
    assert bracket["total_elimination_stages"] >= 1
    assert "champion" in bracket
    assert bracket["champion"]["team"] is not None
    assert bracket["champion"]["institution"] is not None
    assert bracket["is_same_institution_closeout"] is True  # Chaps 2026 had an Ananda closeout
    assert len(bracket["stages"]) > 0

    gf_stage = bracket["stages"][-1]
    assert len(gf_stage["matchups"]) == 1
    gf_match = gf_stage["matchups"][0]
    assert "proposition" in gf_match
    assert "opposition" in gf_match
    assert "result" in gf_match
    assert gf_match["result"]["winner_team"] is not None
    assert "lineup" in gf_match["proposition"]
    assert "lineup" in gf_match["opposition"]


def test_bracket_alias_slsdc(db_conn):
    engine = BracketEngine(db_conn)
    bracket = engine.get_tournament_bracket("slsdc")
    assert bracket is not None
    assert "SLSDC" in bracket["tournament_name"]
    assert bracket["total_elimination_stages"] >= 3  # Quarters, Semis, Final
    stage_names = [s["stage_name"] for s in bracket["stages"]]
    assert any("Final" in name or "Semifinals" in name for name in stage_names)


def test_bracket_non_existent(db_conn):
    engine = BracketEngine(db_conn)
    bracket = engine.get_tournament_bracket("FakeTournament9999")
    assert bracket is None
