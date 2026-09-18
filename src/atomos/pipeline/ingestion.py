"""
Atomos End-to-End Tournament Ingestion Pipeline

Automates the entire data pipeline from public Tabbycat URL to validated SQLite database:
1. Extraction: Scrapes and parses all tablesData into data/raw/<slug>/
2. Normalization: Inserts tournaments, institutions, persons, teams, rounds, debates, ballots, speeches
3. Reconciliation: Resolves missing ballots, classifies out-rounds, byes, iron-mans, and true walkovers
4. Validation: Asserts database relational integrity and rubric validity
"""

import sqlite3
import sys
from pathlib import Path
from typing import Optional

from atomos.database.connection import initialize_database
from atomos.extractor.tabbycat import TabbycatExtractor
from atomos.normalizer.reconciler import TabReconciler
from atomos.normalizer.tournament_normalizer import TournamentNormalizer
from atomos.normalizer.validator import IntegrityValidator


class IngestionPipeline:
    """End-to-end tournament ingestion orchestrator."""

    def __init__(self, db_path: Path = Path("data/atomos.db")):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def ingest_tournament(
        self,
        target: str,
        skip_extract: bool = False,
        verbose: bool = True,
    ) -> dict:
        """
        Ingests a tournament by URL or existing slug.
        :param target: Public Tabbycat URL (e.g., https://site.calicotab.com/slug/) or raw directory slug
        :param skip_extract: If True, uses existing raw data in data/raw/<slug>
        :param verbose: Print progress messages
        """
        def log(msg: str):
            if verbose:
                print(f"[INGEST] {msg}")

        # Determine slug and raw directory
        target_str = target.rstrip("/")
        if target_str.startswith("http://") or target_str.startswith("https://"):
            slug = target_str.split("/")[-1]
            base_url = target_str
        else:
            slug = target_str
            base_url = None

        raw_base_dir = Path("data/raw")
        raw_dir = raw_base_dir / slug

        # STEP 1: EXTRACTION
        if not skip_extract:
            if not base_url:
                raise ValueError(f"Full URL required for extraction. Got: '{target}'")
            log(f"Step 1/4: Extracting tournament from {base_url} into {raw_base_dir}...")
            extractor = TabbycatExtractor()
            extract_data = extractor.extract_tournament(base_url=base_url, output_dir=raw_base_dir)
            slug = extract_data["metadata"]["slug"]
            raw_dir = raw_base_dir / slug
            log(f"Extraction completed successfully for slug '{slug}'.")
        else:
            log(f"Step 1/4: Skipping extraction. Using existing files in {raw_dir}")
            if not raw_dir.exists():
                raise FileNotFoundError(f"Raw data directory does not exist: {raw_dir}")

        # STEP 2: NORMALIZATION
        log(f"Step 2/4: Normalizing {slug} into database {self.db_path}...")
        conn = initialize_database(self.db_path)
        normalizer = TournamentNormalizer(conn)
        tournament_id = normalizer.normalize_tournament(raw_dir)
        log(f"Tournament normalized with internal ID {tournament_id}.")

        # STEP 3: RECONCILIATION
        log(f"Step 3/4: Reconciling speaker tabs, out-rounds, byes, and walkovers...")
        reconciler = TabReconciler(conn)
        rec_res = reconciler.reconcile_tournament(tournament_id, raw_dir)
        log(f"Reconciliation: {rec_res['reconciled_debates']} ballots backfilled, "
            f"{rec_res['elimination_debates']} out-rounds preserved, "
            f"{rec_res['bye_swing_debates']} byes categorized, "
            f"{rec_res['walkover_debates']} true walkovers flagged.")

        # STEP 4: INTEGRITY VALIDATION
        log("Step 4/4: Running integrity validation gatekeeper...")
        validator = IntegrityValidator(conn)
        report = validator.validate()

        if not report.is_valid:
            log(f"WARNING: Integrity check flagged issues: {report.critical_errors}")
        else:
            log("Integrity check passed! 0 critical errors.")

        # Query tournament statistics
        cur = conn.cursor()
        cur.execute("SELECT name FROM tournaments WHERE id = ?", (tournament_id,))
        t_name = cur.fetchone()["name"]

        cur.execute("SELECT COUNT(*) as cnt FROM rounds WHERE tournament_id = ?", (tournament_id,))
        round_count = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM teams WHERE tournament_id = ?", (tournament_id,))
        team_count = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(d.id) as cnt FROM debates d
            JOIN rounds r ON d.round_id = r.id
            WHERE r.tournament_id = ?
        """, (tournament_id,))
        debate_count = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(sp.id) as cnt FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            WHERE r.tournament_id = ? AND sp.total_score > 0
        """, (tournament_id,))
        speech_count = cur.fetchone()["cnt"]

        conn.close()

        summary = {
            "tournament_id": tournament_id,
            "tournament_name": t_name,
            "slug": slug,
            "rounds_count": round_count,
            "teams_count": team_count,
            "debates_count": debate_count,
            "speeches_recorded": speech_count,
            "reconciliation": rec_res,
            "is_valid": report.is_valid,
            "critical_errors": report.critical_errors,
        }
        return summary
