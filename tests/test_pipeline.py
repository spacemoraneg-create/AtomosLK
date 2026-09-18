"""
Tests for Atomos Ingestion Pipeline.
"""

from pathlib import Path
import pytest

from atomos.pipeline.ingestion import IngestionPipeline


class TestIngestionPipeline:
    def test_pipeline_instantiation(self, tmp_path):
        db_path = tmp_path / "test_pipeline.db"
        pipeline = IngestionPipeline(db_path=db_path)
        assert pipeline.db_path == db_path

    def test_pipeline_skip_extract_requires_existing_directory(self, tmp_path):
        db_path = tmp_path / "test_pipeline.db"
        pipeline = IngestionPipeline(db_path=db_path)
        with pytest.raises(FileNotFoundError):
            pipeline.ingest_tournament("non_existent_slug_12345", skip_extract=True, verbose=False)

    def test_pipeline_raw_reprocessing(self, tmp_path):
        # Reprocess aisdc26 if it exists
        raw_dir = Path("data/raw/aisdc26")
        if not raw_dir.exists():
            pytest.skip("data/raw/aisdc26 not available for test")

        db_path = tmp_path / "test_aisdc.db"
        pipeline = IngestionPipeline(db_path=db_path)
        summary = pipeline.ingest_tournament("aisdc26", skip_extract=True, verbose=False)

        assert summary["slug"] == "aisdc26"
        assert summary["rounds_count"] > 0
        assert summary["teams_count"] > 0
        assert summary["debates_count"] > 0
        assert summary["is_valid"] is True
