"""
Unit tests for Atomos Identity Resolver (Levenshtein edit distance <= 2, Spacing, Capitalization)
"""

import sqlite3
import pytest
from pathlib import Path

from atomos.analytics.identity_resolver import (
    IdentityResolver,
    levenshtein_distance_le_2,
    is_placeholder_name,
)


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def test_levenshtein_distance_le_2():
    assert levenshtein_distance_le_2("hello", "hello") == 0
    assert levenshtein_distance_le_2("ashkar", "askar") == 1
    assert levenshtein_distance_le_2("schooman", "schoorman") == 1
    assert levenshtein_distance_le_2("dilasnee", "dilsanee") == 2
    assert levenshtein_distance_le_2("cat", "dog") is None
    assert levenshtein_distance_le_2("short", "much longer string") is None
    assert levenshtein_distance_le_2("ab", "abcde") is None


def test_is_placeholder_name():
    assert is_placeholder_name("Speaker 1") is True
    assert is_placeholder_name("speaker 2") is True
    assert is_placeholder_name("Adjudicator 1") is True
    assert is_placeholder_name("tab") is True
    assert is_placeholder_name("official") is True
    assert is_placeholder_name("Dithira De Silva") is False
    assert is_placeholder_name("Ahmed Ali") is False


def test_person_suggestions_three_rules(memory_db):
    cur = memory_db.cursor()
    # Create tournament, rounds, institution, and teams for activity
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t_id = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name) VALUES (?, 1, 'R1')", (t_id,))
    r_id = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Ananda College', 'AC')")
    inst_id = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AC A', ?)", (t_id, inst_id))
    team_id = cur.lastrowid
    cur.execute("INSERT INTO debates (round_id, debate_id) VALUES (?, 'd1')", (r_id,))
    d_id = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id) VALUES (?)", (d_id,))
    b_id = cur.lastrowid

    # Rule 1 candidates: Capitalization difference
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Dithira De Silva')")
    p1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Dithira de Silva')")
    p2 = cur.lastrowid

    # Add speeches so p1 has 2 speeches, p2 has 1
    for _ in range(2):
        cur.execute(
            "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) "
            "VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 75.0)",
            (b_id, d_id, r_id, team_id, p1)
        )
    cur.execute(
        "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) "
        "VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 74.0)",
        (b_id, d_id, r_id, team_id, p2)
    )

    # Rule 2 candidates: Spacing variation
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('K.W.D. Tharushika')")
    p3 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('K. W. D. Tharushika')")
    p4 = cur.lastrowid

    # Rule 3 candidates: 1 character edit
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Ahmed Ali Ashkar')")
    p5 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Ahmed Ali Askar')")
    p6 = cur.lastrowid

    # Rule 3 candidates: 2 character edits (transposition)
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Sanuli Dilasnee')")
    p7 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Sanuli Dilsanee')")
    p8 = cur.lastrowid

    # Guardrail checks:
    # 1. Placeholders should be ignored
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Speaker 1')")
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Speaker 2')")

    # 2. Different first names sharing a common surname should NOT be suggested
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Binupa Bandara')")
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Vinuja Bandara')")

    memory_db.commit()

    resolver = IdentityResolver(memory_db)
    suggestions = resolver.get_person_suggestions()

    # Rule 1 should be matched at 100% confidence
    rule1_matches = [s for s in suggestions if s["match_type"] == "Exact Match (Capitalization Difference)"]
    assert len(rule1_matches) == 1
    assert rule1_matches[0]["primary"]["id"] == p1
    assert rule1_matches[0]["duplicate"]["id"] == p2
    assert rule1_matches[0]["confidence"] == 100.0

    # Rule 2 should be matched with Spacing / Whitespace Variation
    rule2_matches = [s for s in suggestions if s["match_type"] == "Spacing / Whitespace Variation"]
    assert len(rule2_matches) == 1
    assert {rule2_matches[0]["primary"]["id"], rule2_matches[0]["duplicate"]["id"]} == {p3, p4}
    assert rule2_matches[0]["confidence"] >= 98.0

    # Rule 3 (1 edit) should be matched with 1 Character Change Away
    edit1_matches = [s for s in suggestions if "1 Character Change Away" in s["match_type"]]
    assert len(edit1_matches) == 1
    assert {edit1_matches[0]["primary"]["id"], edit1_matches[0]["duplicate"]["id"]} == {p5, p6}
    assert edit1_matches[0]["confidence"] >= 95.0

    # Rule 3 (2 edits) should be matched with 2 Character Changes Away
    edit2_matches = [s for s in suggestions if "2 Character Changes Away" in s["match_type"]]
    assert len(edit2_matches) == 1
    assert {edit2_matches[0]["primary"]["id"], edit2_matches[0]["duplicate"]["id"]} == {p7, p8}
    assert edit2_matches[0]["confidence"] >= 90.0

    # Ensure placeholders and surname collisions are NOT suggested
    all_suggested_names = []
    for s in suggestions:
        all_suggested_names.append(s["primary"]["canonical_name"])
        all_suggested_names.append(s["duplicate"]["canonical_name"])
    assert "Speaker 1" not in all_suggested_names
    assert "Speaker 2" not in all_suggested_names
    assert not ("Binupa Bandara" in all_suggested_names and "Vinuja Bandara" in all_suggested_names)


def test_team_suggestions_and_suffix_protection(memory_db):
    cur = memory_db.cursor()
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t1_id = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Trinity College', 'TCK')")
    inst_id = cur.lastrowid

    # Same school, same tournament, but distinct team suffixes 'A' vs 'B'
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Trinity College A', ?)", (t1_id, inst_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Trinity College B', ?)", (t1_id, inst_id))

    # Duplicate team: capitalization or typo within same team
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Trinity College C', ?)", (t1_id, inst_id))
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'trinity college c', ?)", (t1_id, inst_id))

    memory_db.commit()

    resolver = IdentityResolver(memory_db)
    team_sugg = resolver.get_team_suggestions()

    # Verify Team A and Team B are NEVER suggested to be merged
    for s in team_sugg:
        n1 = s["primary"]["name"]
        n2 = s["duplicate"]["name"]
        assert not ("Trinity College A" in (n1, n2) and "Trinity College B" in (n1, n2))

    # Verify capitalization duplicate for C is detected
    c_sugg = [s for s in team_sugg if "Trinity College C" in (s["primary"]["name"], s["duplicate"]["name"])]
    assert len(c_sugg) == 1
    assert c_sugg[0]["confidence"] == 100.0


def test_dismissal_tracking(memory_db):
    cur = memory_db.cursor()
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kasun Perera')")
    p1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kasun Pererra')")
    p2 = cur.lastrowid
    memory_db.commit()

    resolver = IdentityResolver(memory_db)
    sugg_before = resolver.get_person_suggestions()
    assert len(sugg_before) == 1

    resolver.dismiss_suggestion("person", p1, p2)
    sugg_after = resolver.get_person_suggestions()
    assert len(sugg_after) == 0


def test_execute_person_merge(memory_db):
    cur = memory_db.cursor()
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t_id = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name) VALUES (?, 1, 'R1')", (t_id,))
    r_id = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Royal College', 'RC')")
    inst_id = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t_id, inst_id))
    team_id = cur.lastrowid
    cur.execute("INSERT INTO debates (round_id, debate_id) VALUES (?, 'd1')", (r_id,))
    d_id = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id) VALUES (?)", (d_id,))
    b_id = cur.lastrowid

    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kaveesha De Silva')")
    p_primary = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kaveesha de Silva')")
    p_dup = cur.lastrowid

    cur.execute(
        "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) "
        "VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 75.0)",
        (b_id, d_id, r_id, team_id, p_dup)
    )
    memory_db.commit()

    resolver = IdentityResolver(memory_db)
    res = resolver.execute_person_merge(primary_id=p_primary, duplicate_id=p_dup)
    assert res["success"] is True

    # Confirm duplicate is removed and speeches transferred
    cur.execute("SELECT id FROM persons WHERE id = ?", (p_dup,))
    assert cur.fetchone() is None
    cur.execute("SELECT COUNT(*) FROM speech_performances WHERE person_id = ?", (p_primary,))
    assert cur.fetchone()[0] == 1

    # Verify idempotent re-merge does not crash with "ID does not exist"
    res_repeat = resolver.execute_person_merge(primary_id=p_primary, duplicate_id=p_dup)
    assert res_repeat["success"] is True
    assert "already been merged" in res_repeat["message"]
