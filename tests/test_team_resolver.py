"""
Unit tests for Atomos Team Resolver & Grouping Engine
"""

import sqlite3
import pytest
from pathlib import Path
from atomos.normalizer.team_resolver import (
    TeamResolver,
    TeamSummary,
    CandidateTeamResolution,
    VALID_TIERS,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def setup_test_data(conn: sqlite3.Connection):
    cur = conn.cursor()
    # Create tournament
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES (?, ?, ?)", ("t1", "Tournament 1", "http://t1"))
    t_id = cur.lastrowid

    # Create institutions
    cur.execute("INSERT INTO institutions (name, code) VALUES (?, ?)", ("Bishop's College", "BC"))
    bc_id = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES (?, ?)", ("Asian International School", "AIS"))
    ais_id = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES (?, ?)", ("Ladies' College", "LC"))
    lc_id = cur.lastrowid

    # Create persons
    cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", ("Debater 1",))
    p1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", ("Debater 2",))
    p2 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", ("Debater 3",))
    p3 = cur.lastrowid

    # Create teams
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'BC A', ?)", (t_id, bc_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'BC Gold', ?)", (t_id, bc_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'BC Purple', ?)", (t_id, bc_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AIS Green', ?)", (t_id, ais_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AIS Blue', ?)", (t_id, ais_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'LC Red', ?)", (t_id, lc_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Swing Team', NULL)", (t_id,))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'BYE', NULL)", (t_id,))

    # Create team with debaters to test roster overlap
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'BC Custom', ?)", (t_id, bc_id))
    custom_team_id = cur.lastrowid

    # Standard BC A team
    cur.execute("SELECT id FROM teams WHERE name = 'BC A'")
    bc_a_id = cur.fetchone()[0]

    # Assign members
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (bc_a_id, p1))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (bc_a_id, p2))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (custom_team_id, p1))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (custom_team_id, p2))

    conn.commit()


def test_standard_suffix_inference(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM teams WHERE name = 'BC A'")
    t_id = cur.fetchone()[0]

    cands = resolver.find_candidate_resolutions()
    cand = next(c for c in cands if c.team.id == t_id)

    assert cand.suggested_canonical_name == "BC A"
    assert cand.suggested_tier == "A"
    assert cand.match_type == "STANDARD_SUFFIX"
    assert cand.confidence == 1.0


def test_school_alias_inference(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cands = resolver.find_candidate_resolutions()

    cand_gold = next(c for c in cands if c.team.raw_name == "BC Gold")
    assert cand_gold.suggested_canonical_name == "BC A"
    assert cand_gold.suggested_tier == "A"
    assert cand_gold.confidence >= 0.95

    cand_purple = next(c for c in cands if c.team.raw_name == "BC Purple")
    assert cand_purple.suggested_canonical_name == "BC B"
    assert cand_purple.suggested_tier == "B"
    assert cand_purple.confidence >= 0.95

    cand_green = next(c for c in cands if c.team.raw_name == "AIS Green")
    assert cand_green.suggested_canonical_name == "AIS A"
    assert cand_green.suggested_tier == "A"

    cand_blue = next(c for c in cands if c.team.raw_name == "AIS Blue")
    assert cand_blue.suggested_canonical_name == "AIS B"
    assert cand_blue.suggested_tier == "B"


def test_swing_and_bye_inference(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cands = resolver.find_candidate_resolutions()

    cand_swing = next(c for c in cands if c.team.raw_name == "Swing Team")
    assert cand_swing.suggested_canonical_name == "Swing"
    assert cand_swing.suggested_tier == "SWING"
    assert cand_swing.confidence == 1.0

    cand_bye = next(c for c in cands if c.team.raw_name == "BYE")
    assert cand_bye.suggested_canonical_name == "BYE"
    assert cand_bye.suggested_tier == "OTHER"
    assert cand_bye.confidence == 1.0


def test_roster_overlap_inference(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cands = resolver.find_candidate_resolutions()
    cand_custom = next(c for c in cands if c.team.raw_name == "BC Custom")

    assert cand_custom.suggested_canonical_name == "BC A"
    assert cand_custom.suggested_tier == "A"
    assert cand_custom.match_type == "ROSTER_OVERLAP"
    assert cand_custom.confidence >= 0.80
    assert "Debater 1" in cand_custom.reason


def test_resolve_team_persists(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM teams WHERE name = 'BC Gold'")
    t_id = cur.fetchone()[0]

    success = resolver.resolve_team(
        team_id=t_id,
        canonical_name="BC A",
        tier="A",
        reason="Manual review",
        reviewed_by_user=True,
    )
    assert success is True

    # Check teams table
    cur.execute("SELECT canonical_name, tier FROM teams WHERE id = ?", (t_id,))
    row = cur.fetchone()
    assert row[0] == "BC A"
    assert row[1] == "A"

    # Check team_resolutions table
    cur.execute("SELECT canonical_name, tier, status, reviewed_by_user FROM team_resolutions WHERE team_id = ?", (t_id,))
    res_row = cur.fetchone()
    assert res_row["canonical_name"] == "BC A"
    assert res_row["tier"] == "A"
    assert res_row["status"] == "CONFIRMED"
    assert res_row["reviewed_by_user"] == 1


def test_group_teams(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM teams WHERE name IN ('BC A', 'BC Gold')")
    ids = [r[0] for r in cur.fetchall()]

    count = resolver.group_teams(ids, canonical_name="BC A", tier="A", reason="Batch test")
    assert count == len(ids)

    for tid in ids:
        s = resolver.get_team_summary(tid)
        assert s.canonical_name == "BC A"
        assert s.tier == "A"
        assert s.status == "RESOLVED"


def test_auto_resolve_safe(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    resolved_count = resolver.auto_resolve_safe(min_confidence=0.90)
    assert resolved_count >= 5

    # Check pending
    pending = resolver.find_candidate_resolutions(unresolved_only=True)
    assert len(pending) < 3


def test_invalid_tier_rejected(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM teams LIMIT 1")
    t_id = cur.fetchone()[0]

    with pytest.raises(ValueError, match="Invalid tier"):
        resolver.resolve_team(team_id=t_id, canonical_name="Test", tier="INVALID")


def test_reset_resolutions(db_conn):
    setup_test_data(db_conn)
    resolver = TeamResolver(db_conn)

    resolver.auto_resolve_safe(min_confidence=0.90)
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM teams WHERE canonical_name IS NOT NULL")
    assert cur.fetchone()[0] > 0

    # Reset
    reset_count = resolver.reset_resolutions()
    assert reset_count > 0

    cur.execute("SELECT COUNT(*) FROM teams WHERE canonical_name IS NOT NULL")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM team_resolutions")
    assert cur.fetchone()[0] == 0
