"""
Tests for Atomos TabReconciler.
"""

import sqlite3
from pathlib import Path
import pytest

from atomos.normalizer.reconciler import TabReconciler
from atomos.normalizer.validator import IntegrityValidator
from atomos.normalizer.tournament_normalizer import TournamentNormalizer
from atomos.database.connection import get_connection


@pytest.fixture
def in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


class TestTabReconcilerCategories:
    def test_reconcile_real_tournament_categories(self, in_memory_db):
        raw_dir = Path("data/raw/vijis26")
        if not raw_dir.exists():
            pytest.skip("data/raw/vijis26 does not exist")

        normalizer = TournamentNormalizer(in_memory_db)
        t_id = normalizer.normalize_tournament(raw_dir)

        reconciler = TabReconciler(in_memory_db)
        res = reconciler.reconcile_tournament(t_id, raw_dir)

        # Elimination rounds must be recognized and not flagged as walkovers
        assert res["elimination_debates"] == 23
        assert res["bye_swing_debates"] == 3
        # 4 authentic walkovers under Chief Adj rule (R1 DIS vs SGCK C, R1 LC Mithsi vs SGCK A, R3 SJC vs HFBV, R5 STPS vs SACK B)
        assert res["walkover_debates"] == 4

        cur = in_memory_db.cursor()
        # Verify that all walkovers have declared winners on their ballots and 0 speeches
        cur.execute("""
            SELECT d.id, b.winner_side, b.prop_total_score, b.opp_total_score,
                   (SELECT COUNT(*) FROM speech_performances sp WHERE sp.debate_id = d.id) as spk_cnt
            FROM debates d
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 1
        """)
        wo_rows = cur.fetchall()
        assert len(wo_rows) == 4
        for wo in wo_rows:
            assert wo["winner_side"] in ("Proposition", "Opposition")
            assert wo["prop_total_score"] is None
            assert wo["opp_total_score"] is None
            assert wo["spk_cnt"] == 0
        # Verify that elimination rounds have is_walkover = 0
        cur.execute("""
            SELECT COUNT(*) as cnt FROM debates d
            JOIN rounds r ON d.round_id = r.id
            WHERE r.round_number >= 6 AND d.is_walkover = 1
        """)
        assert cur.fetchone()["cnt"] == 0

        # Run integrity validator
        validator = IntegrityValidator(in_memory_db)
        report = validator.validate()
        assert report.is_valid is True
        assert len(report.critical_errors) == 0

    def test_reconstruct_missing_debates_from_tabs_on_metho(self):
        conn = get_connection()
        cur = conn.cursor()

        # The 3 debates with 500 server errors on Tabbycat must be reconstructed
        cur.execute("""
            SELECT d.debate_id, d.is_walkover, b.prop_total_score, b.opp_total_score, b.winner_side, b.adjudicator_raw_name,
                   COUNT(sp.id) as spk_cnt
            FROM debates d
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            JOIN speech_performances sp ON d.id = sp.debate_id
            WHERE d.debate_id IN ('642704', '643040', '643195')
            GROUP BY d.id
        """)
        reconstructed = cur.fetchall()
        assert len(reconstructed) == 3
        for r in reconstructed:
            assert r["is_walkover"] == 0
            assert r["spk_cnt"] >= 4
            assert "Reconstructed" in r["adjudicator_raw_name"]
            assert r["winner_side"] in ["Proposition", "Opposition"]

        # Out-rounds on Metho (R6..R9) must have 0 walkovers
        cur.execute("""
            SELECT COUNT(*) as cnt FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            WHERE t.slug = 'metho2026' AND r.round_number >= 6 AND d.is_walkover = 1
        """)
        assert cur.fetchone()["cnt"] == 0

        # Run integrity validator
        validator = IntegrityValidator(conn)
        report = validator.validate()
        assert report.is_valid is True
        assert len(report.critical_errors) == 0

