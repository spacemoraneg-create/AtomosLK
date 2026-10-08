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
from typing import Callable, Optional

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
        hosting_dates: Optional[str] = None,
        verbose: bool = True,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> dict:
        """
        Ingests a tournament by URL or existing slug.
        :param target: Public Tabbycat URL (e.g., https://site.calicotab.com/slug/) or raw directory slug
        :param skip_extract: If True, uses existing raw data in data/raw/<slug>
        :param hosting_dates: Optional manual dates when the tournament took place (e.g. 'Oct 12–15, 2026')
        :param verbose: Print progress messages
        :param progress_callback: Optional callback receiving (step_key, message)
        """
        def log(msg: str, step: str = ""):
            if verbose:
                print(f"[INGEST] {msg}")
            if progress_callback:
                progress_callback(step or msg, msg)

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
                if raw_dir.exists():
                    log(f"Target '{target}' is a local slug and '{raw_dir}' exists. Using existing raw files.")
                    skip_extract = True
                else:
                    raise ValueError(f"Full URL required for extraction or existing raw directory '{raw_dir}' not found.")
            else:
                log(f"Step 1/4: Extracting tournament from {base_url} into {raw_base_dir}...", step="EXTRACTING")
                extractor = TabbycatExtractor()
                extract_data = extractor.extract_tournament(base_url=base_url, output_dir=raw_base_dir)
                slug = (
                    extract_data.get("metadata", {}).get("tournament_slug")
                    or extract_data.get("metadata", {}).get("slug")
                    or extract_data.get("tournament_slug", slug)
                )
                raw_dir = raw_base_dir / slug
                log(f"Extraction completed successfully for slug '{slug}'.", step="EXTRACTED")

        if skip_extract:
            log(f"Step 1/4: Skipping extraction. Using existing files in {raw_dir}", step="SKIPPED_EXTRACT")
            if not raw_dir.exists():
                raise FileNotFoundError(f"Raw data directory does not exist: {raw_dir}")

        # STEP 2: NORMALIZATION
        log(f"Step 2/4: Normalizing {slug} into database {self.db_path}...", step="NORMALIZING")
        conn = initialize_database(self.db_path)
        normalizer = TournamentNormalizer(conn)
        tournament_id = normalizer.normalize_tournament(raw_dir)
        log(f"Tournament normalized with internal ID {tournament_id}.", step="NORMALIZED")

        if hosting_dates and hosting_dates.strip():
            conn.execute("UPDATE tournaments SET hosting_dates = ? WHERE id = ?", (hosting_dates.strip(), tournament_id))
            conn.commit()
            log(f"Persisted manual tournament hosting dates: '{hosting_dates.strip()}'.", step="DATES_PERSISTED")

        # STEP 3: RECONCILIATION
        log(f"Step 3/4: Reconciling speaker tabs, out-rounds, byes, and walkovers...", step="RECONCILING")
        reconciler = TabReconciler(conn)
        rec_res = reconciler.reconcile_tournament(tournament_id, raw_dir)
        log(f"Reconciliation: {rec_res['reconciled_debates']} ballots backfilled, "
            f"{rec_res['elimination_debates']} out-rounds preserved, "
            f"{rec_res['bye_swing_debates']} byes categorized, "
            f"{rec_res['walkover_debates']} true walkovers flagged.", step="RECONCILED")

        # STEP 3.5: TEAM RESOLUTION & MERGE PROPAGATION
        try:
            from atomos.normalizer.team_resolver import TeamResolver
            cur_tr = conn.cursor()
            # 1. Propagate confirmed_team_merges and historical canonical mappings for same (institution_id, name)
            cur_tr.execute("""
                SELECT id, institution_id, name FROM teams
                WHERE tournament_id = ? AND (canonical_name IS NULL OR tier IS NULL)
            """, (tournament_id,))
            unresolved_rows = cur_tr.fetchall()
            tr_engine = TeamResolver(conn)
            for u_row in unresolved_rows:
                u_id, u_inst, u_name = u_row["id"], u_row["institution_id"], u_row["name"]
                if not u_inst:
                    continue
                # Check confirmed_team_merges first
                cur_tr.execute("""
                    SELECT name FROM sqlite_master WHERE type='table' AND name='confirmed_team_merges'
                """)
                has_cm = cur_tr.fetchone() is not None
                matched_canon, matched_tier = None, None
                if has_cm:
                    cur_tr.execute("""
                        SELECT target_canonical_name FROM confirmed_team_merges
                        WHERE institution_id = ? AND LOWER(variant_name) = LOWER(?)
                        LIMIT 1
                    """, (u_inst, u_name))
                    cm_row = cur_tr.fetchone()
                    if cm_row:
                        matched_canon = cm_row[0]
                if not matched_canon:
                    cur_tr.execute("""
                        SELECT canonical_name, tier FROM teams
                        WHERE institution_id = ? AND LOWER(name) = LOWER(?) AND canonical_name IS NOT NULL AND id != ?
                        ORDER BY id DESC LIMIT 1
                    """, (u_inst, u_name, u_id))
                    hist_row = cur_tr.fetchone()
                    if hist_row:
                        matched_canon, matched_tier = hist_row[0], hist_row[1]
                if matched_canon:
                    if not matched_tier:
                        matched_tier = "B" if matched_canon.endswith(" B") else ("C" if matched_canon.endswith(" C") else "A")
                    tr_engine.resolve_team(
                        team_id=u_id,
                        canonical_name=matched_canon,
                        tier=matched_tier,
                        reason="Propagated from historical institution team merge",
                        reviewed_by_user=True,
                        confidence=1.0,
                        status="CONFIRMED",
                    )
            # 2. Run TeamResolver for any remaining unresolved teams
            for cand in tr_engine.find_candidate_resolutions(unresolved_only=True):
                tr_engine.resolve_team(
                    team_id=cand.team.id,
                    canonical_name=cand.suggested_canonical_name,
                    tier=cand.suggested_tier,
                    reason=cand.reason,
                    reviewed_by_user=False,
                    confidence=cand.confidence,
                    status="CONFIRMED",
                )
        except Exception as tr_err:
            log(f"Note: Team auto-resolution warning: {tr_err}")

        # STEP 4: INTEGRITY VALIDATION
        log("Step 4/4: Running integrity validation gatekeeper...", step="VALIDATING")
        validator = IntegrityValidator(conn)
        report = validator.validate(tournament_id=tournament_id)

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
