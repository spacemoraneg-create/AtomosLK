"""
Unit tests for Atomos Identity Merger Engine
"""

import sqlite3
import pytest
from pathlib import Path
from atomos.normalizer.identity_merger import IdentityMerger


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
    cur.execute(
        "INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')"
    )
    t_id = cur.lastrowid

    # Create institution
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Royal College', 'RC')")
    inst_id = cur.lastrowid

    # Create two persons: canonical and duplicate
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kaveesha De Silva')")
    p1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kaveesha de Silva')")
    p2 = cur.lastrowid

    # Create team
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t_id, inst_id))
    team1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC B', ?)", (t_id, inst_id))
    team2 = cur.lastrowid

    # Add team members: p1 on team1, p2 on team2, AND both on team1 (to test collision handling)
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team1, p1))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team2, p2))

    # Add round and debate
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name) VALUES (?, 1, 'Round 1')", (t_id,))
    r_id = cur.lastrowid
    cur.execute(
        "INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd1', ?, ?)",
        (r_id, team1, team2),
    )
    d_id = cur.lastrowid

    # Add ballot
    cur.execute(
        "INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score) VALUES (?, 225.0, 220.0)",
        (d_id,),
    )
    b_id = cur.lastrowid

    # Add speech performances: 1 for p1, 1 for p2
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
        VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 75.0)
        """,
        (b_id, d_id, r_id, team1, p1),
    )
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
        VALUES (?, ?, ?, ?, ?, 'Opposition', '1st', 'SUBSTANTIVE', 74.0)
        """,
        (b_id, d_id, r_id, team2, p2),
    )

    # Add roles
    cur.execute("INSERT INTO tournament_roles (tournament_id, person_id, role, institution_id) VALUES (?, ?, 'DEBATER', ?)", (t_id, p1, inst_id))
    cur.execute("INSERT INTO tournament_roles (tournament_id, person_id, role, institution_id) VALUES (?, ?, 'DEBATER', ?)", (t_id, p2, inst_id))

    # Add alias
    cur.execute("INSERT INTO person_aliases (person_id, raw_name) VALUES (?, 'Kaveesha de Silva')", (p2,))

    # Add identity resolution
    cur.execute(
        """
        INSERT INTO identity_resolutions (raw_name_a, raw_name_b, person_a_id, person_b_id, status, confidence_score, reason)
        VALUES ('Kaveesha De Silva', 'Kaveesha de Silva', ?, ?, 'PENDING_REVIEW', 0.95, 'Case difference')
        """,
        (p1, p2),
    )

    conn.commit()
    return t_id, inst_id, p1, p2, team1, team2


class TestIdentityMerger:

    def test_merge_persons_relational_integrity(self, db_conn):
        t_id, inst_id, p1, p2, team1, team2 = setup_test_data(db_conn)
        merger = IdentityMerger(db_conn)

        # Merge p2 into p1
        success = merger.merge_persons(canonical_id=p1, duplicate_id=p2)
        assert success is True

        cur = db_conn.cursor()

        # p2 should no longer exist in persons
        cur.execute("SELECT id FROM persons WHERE id = ?", (p2,))
        assert cur.fetchone() is None

        # p1 should have 2 speeches now
        cur.execute("SELECT COUNT(*) FROM speech_performances WHERE person_id = ?", (p1,))
        assert cur.fetchone()[0] == 2

        # p1 should be on both teams
        cur.execute("SELECT COUNT(*) FROM team_members WHERE person_id = ?", (p1,))
        assert cur.fetchone()[0] == 2

        # Role collisions resolved: p1 should have exactly 1 role for this tournament
        cur.execute("SELECT COUNT(*) FROM tournament_roles WHERE person_id = ?", (p1,))
        assert cur.fetchone()[0] == 1

        # Aliases: 'Kaveesha de Silva' should be mapped to p1
        cur.execute("SELECT person_id FROM person_aliases WHERE raw_name = 'Kaveesha de Silva'")
        assert cur.fetchone()[0] == p1

        # Resolution status: should be CONFIRMED_MATCH and reviewed_by_user = 1
        cur.execute(
            "SELECT status, reviewed_by_user FROM identity_resolutions WHERE person_a_id = ? OR person_b_id = ?",
            (p1, p1),
        )
        res = cur.fetchone()
        assert res is not None
        assert res["status"] == "CONFIRMED_MATCH"
        assert res["reviewed_by_user"] == 1


        # Foreign key integrity check must pass with 0 errors
        cur.execute("PRAGMA foreign_key_check;")
        assert len(cur.fetchall()) == 0

    def test_merge_handles_existing_team_membership_collision(self, db_conn):
        t_id, inst_id, p1, p2, team1, team2 = setup_test_data(db_conn)
        cur = db_conn.cursor()
        # Also assign p2 to team1 where p1 already belongs
        cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team1, p2))
        db_conn.commit()

        merger = IdentityMerger(db_conn)
        # Should not raise UNIQUE constraint error
        success = merger.merge_persons(canonical_id=p1, duplicate_id=p2)
        assert success is True

        cur.execute("PRAGMA foreign_key_check;")
        assert len(cur.fetchall()) == 0

    def test_reject_match_permanence(self, db_conn):
        t_id, inst_id, p1, p2, team1, team2 = setup_test_data(db_conn)
        merger = IdentityMerger(db_conn)

        merger.reject_match(p1, p2, "Different debaters with same name")

        cur = db_conn.cursor()
        cur.execute(
            "SELECT status, reviewed_by_user FROM identity_resolutions WHERE (person_a_id = ? AND person_b_id = ?)",
            (p1, p2),
        )
        row = cur.fetchone()
        assert row["status"] == "CONFIRMED_DIFFERENT"
        assert row["reviewed_by_user"] == 1

        # Candidate pairs should not return this pair anymore
        candidates = merger.find_candidate_pairs()
        pair_ids = [(c.person_a.id, c.person_b.id) for c in candidates]
        assert (p1, p2) not in pair_ids and (p2, p1) not in pair_ids

    def test_custom_canonical_name(self, db_conn):
        t_id, inst_id, p1, p2, team1, team2 = setup_test_data(db_conn)
        merger = IdentityMerger(db_conn)

        merger.merge_persons(canonical_id=p1, duplicate_id=p2, canonical_name="Kaveesha de Silva (Cap)")

        cur = db_conn.cursor()
        cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (p1,))
        assert cur.fetchone()["canonical_name"] == "Kaveesha de Silva (Cap)"

    def test_candidate_discovery_types(self, db_conn):
        cur = db_conn.cursor()
        # Create persons to trigger each discovery category
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Dithira De Silva')")
        p_exact1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Dithira de Silva')")
        p_exact2 = cur.lastrowid

        cur.execute("INSERT INTO persons (canonical_name) VALUES ('S. M. Yuthmi')")
        p_space1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('S.M. Yuthmi')")
        p_space2 = cur.lastrowid

        db_conn.commit()
        merger = IdentityMerger(db_conn)
        candidates = merger.find_candidate_pairs()

        match_types = {c.match_type for c in candidates}
        assert "EXACT_CASE" in match_types
        assert "SPACING_PUNCTUATION" in match_types

    def test_candidate_discovery_extended_types(self, db_conn):
        cur = db_conn.cursor()
        cur.execute("INSERT INTO institutions (name, code) VALUES ('Test College', 'TC')")
        inst_id = cur.lastrowid
        cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t_ext', 'Tournament Ext', 'http://ext')")
        t_id = cur.lastrowid
        cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'TC A', ?)", (t_id, inst_id))
        team_id = cur.lastrowid

        # 1. NAME_INVERSION
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Jathuran Selvendra')")
        p_inv1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Selvendra Jathuran')")
        p_inv2 = cur.lastrowid

        # 2. MIDDLE_NAME
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kumal Premathunga')")
        p_mid1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Kumal Seniru Premathunga')")
        p_mid2 = cur.lastrowid

        # 3. SINGLE_NAME
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Ananya')")
        p_sng1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Ananya Nandakumar')")
        p_sng2 = cur.lastrowid

        # Link all to the same institution via team_members
        for pid in [p_inv1, p_inv2, p_mid1, p_mid2, p_sng1, p_sng2]:
            cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_id, pid))

        db_conn.commit()

        merger = IdentityMerger(db_conn)
        candidates = merger.find_candidate_pairs()
        types = {c.match_type for c in candidates}

        assert "NAME_INVERSION" in types
        assert "MIDDLE_NAME" in types
        assert "SINGLE_NAME" in types

    def test_debate_collision_prevention(self, db_conn):
        cur = db_conn.cursor()
        cur.execute("INSERT INTO institutions (name, code) VALUES ('Col College', 'CC')")
        inst_id = cur.lastrowid
        cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t_col', 'Tournament Col', 'http://col')")
        t_id = cur.lastrowid
        cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'CC A', ?)", (t_id, inst_id))
        team1 = cur.lastrowid
        cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'CC B', ?)", (t_id, inst_id))
        team2 = cur.lastrowid

        # Two debaters with very similar names who debated against each other
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Shenu Sadew')")
        p1 = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Shanu Sadew')")
        p2 = cur.lastrowid

        cur.execute("INSERT INTO rounds (tournament_id, round_number, name) VALUES (?, 1, 'R1')", (t_id,))
        r_id = cur.lastrowid
        cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_col', ?, ?)", (r_id, team1, team2))
        d_id = cur.lastrowid
        cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score) VALUES (?, 220, 210)", (d_id,))
        b_id = cur.lastrowid

        cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 70)", (b_id, d_id, r_id, team1, p1))
        cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Opposition', '1st', 'SUBSTANTIVE', 70)", (b_id, d_id, r_id, team2, p2))

        cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team1, p1))
        cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team2, p2))
        db_conn.commit()

        merger = IdentityMerger(db_conn)
        # Collision check must report True
        assert merger.has_debate_collision(p1, p2) is True

        # Candidate pairs must NOT include this pair
        candidates = merger.find_candidate_pairs()
        candidate_pairs = {(min(c.person_a.id, c.person_b.id), max(c.person_a.id, c.person_b.id)) for c in candidates}
        assert (min(p1, p2), max(p1, p2)) not in candidate_pairs

        # Merging with check_collision=True must raise ValueError
        with pytest.raises(ValueError, match="both competed in the same debate"):
            merger.merge_persons(canonical_id=p1, duplicate_id=p2, check_collision=True)

