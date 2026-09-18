"""
Tests for Atomos Database Schema and Tournament Normalizer.
"""

import sqlite3
from pathlib import Path
import pytest

from atomos.database.connection import initialize_database
from atomos.normalizer.tournament_normalizer import TournamentNormalizer
from atomos.normalizer.validator import IntegrityValidator



@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database initialized with the schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


class TestDatabaseSchema:
    def test_tables_created(self, in_memory_db):
        cur = in_memory_db.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cur.fetchall()}
        expected = {
            "institutions",
            "persons",
            "person_aliases",
            "identity_resolutions",
            "tournaments",
            "tournament_roles",
            "teams",
            "team_members",
            "rounds",
            "debates",
            "adjudicator_assignments",
            "adjudicator_ballots",
            "speech_performances",
            "provenance_records",
        }
        for exp in expected:
            assert exp in tables, f"Expected table {exp} missing"

    def test_foreign_keys_enforced(self, in_memory_db):
        cur = in_memory_db.cursor()
        # Inserting a round with non-existent tournament should fail
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO rounds (tournament_id, round_number, name) VALUES (9999, 1, 'Round 1')"
            )


class TestTournamentNormalizer:
    def test_normalize_vijis26(self, in_memory_db):
        raw_dir = Path("data/raw/vijis26")
        if not raw_dir.exists():
            pytest.skip("data/raw/vijis26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        t_id = normalizer.normalize_tournament(raw_dir)
        assert t_id > 0

        cur = in_memory_db.cursor()

        # Check tournament record
        cur.execute("SELECT * FROM tournaments WHERE id = ?", (t_id,))
        t_row = cur.fetchone()
        assert t_row["slug"] == "vijis26"
        assert "Vijitha Weerasinghe" in t_row["name"]

        # Check teams count (VJIS 26 had 71 teams)
        cur.execute("SELECT COUNT(*) as cnt FROM teams WHERE tournament_id = ?", (t_id,))
        assert cur.fetchone()["cnt"] == 71

        # Check debaters and adjudicators populated
        cur.execute("SELECT COUNT(*) as cnt FROM persons")
        assert cur.fetchone()["cnt"] > 200

        # Check debates and speech performances
        cur.execute("SELECT COUNT(*) as cnt FROM debates")
        debates_cnt = cur.fetchone()["cnt"]
        assert debates_cnt > 0

        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances")
        speeches_cnt = cur.fetchone()["cnt"]
        assert speeches_cnt > 0

        # Verify speech components exist and are within bounds
        cur.execute("SELECT * FROM speech_performances WHERE content IS NOT NULL LIMIT 5")
        rows = cur.fetchall()
        assert len(rows) > 0
        for r in rows:
            if r["speech_type"] == "SUBSTANTIVE":
                assert 24 <= r["content"] <= 32
                assert 24 <= r["style"] <= 32
                assert 12 <= r["strategy"] <= 16

    def test_strict_identity_resolution_flags_similar_names(self, in_memory_db):
        normalizer = TournamentNormalizer(in_memory_db)
        # Create a tournament
        cur = in_memory_db.cursor()
        cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
        t_id = cur.lastrowid

        # Add "Balishta Wijesinghe"
        p1 = normalizer.get_or_create_person("Balishta Wijesinghe", t_id)
        # Add "B. Wijesinghe"
        p2 = normalizer.get_or_create_person("B. Wijesinghe", t_id)

        # Must NOT automatically merge them
        assert p1 != p2

        # Must log an entry in identity_resolutions with PENDING_REVIEW
        cur.execute("SELECT * FROM identity_resolutions WHERE status = 'PENDING_REVIEW'")
        resolutions = cur.fetchall()
        assert len(resolutions) > 0
        res = resolutions[0]
        assert "Wijesinghe" in res["raw_name_a"] or "Wijesinghe" in res["raw_name_b"]
        assert res["reviewed_by_user"] == 0

    def test_normalize_novice_teams_on_apiit(self, in_memory_db):
        apiit_dir = Path("data/raw/apiitisdc2026")
        if not apiit_dir.exists():
            pytest.skip("data/raw/apiitisdc2026 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        t_id = normalizer.normalize_tournament(apiit_dir)

        cur = in_memory_db.cursor()
        # Verify that Novice teams exist in the teams table
        cur.execute("SELECT COUNT(*) as cnt FROM teams WHERE tournament_id = ? AND category = 'NOVICE'", (t_id,))
        novice_count = cur.fetchone()["cnt"]
        assert novice_count > 0, "Expected novice teams to be classified as NOVICE"

    def test_normalize_paneled_ballots_on_slsdc(self, in_memory_db):
        slsdc_dir = Path("data/raw/slsdc26")
        if not slsdc_dir.exists():
            pytest.skip("data/raw/slsdc26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        t_id = normalizer.normalize_tournament(slsdc_dir)

        cur = in_memory_db.cursor()
        # Verify that multiple ballots exist for debate 676447
        cur.execute(
            """
            SELECT COUNT(b.id) as ballot_cnt 
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            WHERE d.debate_id = '676447'
            """
        )
        row = cur.fetchone()
        assert row["ballot_cnt"] == 2, "Expected 2 adjudicator ballots for paneled debate 676447"

    def test_debates_have_no_unlinked_teams(self, in_memory_db):
        vijis_dir = Path("data/raw/vijis26")
        if not vijis_dir.exists():
            pytest.skip("data/raw/vijis26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        normalizer.normalize_tournament(vijis_dir)

        cur = in_memory_db.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM debates WHERE prop_team_id IS NULL OR opp_team_id IS NULL")
        unlinked_count = cur.fetchone()["cnt"]
        assert unlinked_count == 0, f"Expected 0 unlinked debates, found {unlinked_count}"

    def test_speech_rubric_validity_flag(self, in_memory_db):
        vijis_dir = Path("data/raw/vijis26")
        if not vijis_dir.exists():
            pytest.skip("data/raw/vijis26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        normalizer.normalize_tournament(vijis_dir)

        cur = in_memory_db.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances WHERE is_valid_rubric = 1")
        valid_cnt = cur.fetchone()["cnt"]
        assert valid_cnt > 0, "Expected majority of speeches to have valid rubric"

    def test_integrity_validator_guarantees_clean_database(self, in_memory_db):
        raw_dir = Path("data/raw/vijis26")
        if not raw_dir.exists():
            pytest.skip("data/raw/vijis26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        normalizer.normalize_tournament(raw_dir)

        validator = IntegrityValidator(in_memory_db)
        report = validator.validate()
        assert report.is_valid is True, f"Integrity check failed: {report.critical_errors}"
        assert len(report.critical_errors) == 0


