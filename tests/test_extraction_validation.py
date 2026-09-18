"""
Integration verification tests across all extracted live tournaments:
- VJIS '26 (Dr. Vijitha Weerasinghe Memorial)
- AISDC 2026 (AIS Debating Championship)
- APIIT ISDC 2026 (Novice & Open Tournament)
- SLSDC 2026 (Sri Lanka Schools Debating Championship)
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path("data/raw")


class TestMultiTournamentDataIntegrity:
    def test_all_tournaments_manifests_exist(self):
        slugs = ["vijis26", "aisdc26", "apiitisdc2026", "slsdc26"]
        for slug in slugs:
            t_dir = DATA_DIR / slug
            assert t_dir.exists(), f"Tournament dir {slug} missing"
            manifest_file = t_dir / "manifest.json"
            assert manifest_file.exists(), f"Manifest for {slug} missing"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            assert manifest["tournament_slug"] == slug
            assert len(manifest["rounds_extracted"]) > 0
            assert manifest["version"] == "2.11.0-c" or "2.11.0" in manifest["version"]

    def test_apiit_novice_tabs_extracted(self):
        """Verify that Novice tabs in Novice&Open tournaments are successfully extracted."""
        apiit_dir = DATA_DIR / "apiitisdc2026"
        manifest = json.loads((apiit_dir / "manifest.json").read_text(encoding="utf-8"))
        assert "tab_team_novice" in manifest["tabs_extracted"]
        assert "tab_speaker_novice" in manifest["tabs_extracted"]
        assert "tab_team" in manifest["tabs_extracted"]
        assert "tab_speaker" in manifest["tabs_extracted"]

        novice_team_file = apiit_dir / "tab_team_novice.json"
        assert novice_team_file.exists()
        novice_teams = json.loads(novice_team_file.read_text(encoding="utf-8"))
        assert len(novice_teams[0]["data"]) > 0

    def test_aisdc_institutions_and_replies_extracted(self):
        """Verify that institutions and replies tab on AISDC are extracted."""
        aisdc_dir = DATA_DIR / "aisdc26"
        manifest = json.loads((aisdc_dir / "manifest.json").read_text(encoding="utf-8"))
        assert "tab_replies" in manifest["tabs_extracted"]
        assert "participants_institutions" in manifest["participants_extracted"]

        inst_file = aisdc_dir / "participants_institutions.json"
        assert inst_file.exists()
        inst_data = json.loads(inst_file.read_text(encoding="utf-8"))
        assert len(inst_data[0]["data"]) == 15

    def test_slsdc_paneled_multi_adjudicator_ballots(self):
        """Verify that paneled debates capture multiple adjudicators with distinct ballots."""
        slsdc_dir = DATA_DIR / "slsdc26"
        scoresheets_dir = slsdc_dir / "scoresheets"
        paneled_debate_file = scoresheets_dir / "debate_676447.json"
        assert paneled_debate_file.exists()

        data = json.loads(paneled_debate_file.read_text(encoding="utf-8"))
        assert data["debate_id"] == "676447"
        # Paneled debate has 2 adjudicators
        assert len(data["ballots"]) == 2
        names = [b["adjudicator_name"] for b in data["ballots"]]
        assert "Adam Dhilshan" in names
        assert "Amnah Jiffrey" in names

        for b in data["ballots"]:
            assert b["proposition"]["team_name"] == "AIS Green"
            assert b["opposition"]["team_name"] == "AC B"
            assert len(b["proposition"]["speeches"]) == 4
            assert len(b["opposition"]["speeches"]) == 4
            # Verify speeches have Content, Style, Strategy
            s1 = b["proposition"]["speeches"][0]
            assert s1["content"] is not None
            assert s1["style"] is not None
            assert s1["strategy"] is not None

    def test_motions_and_statistics_extracted(self):
        """Verify that motions and motion balance statistics are saved."""
        slsdc_dir = DATA_DIR / "slsdc26"
        assert (slsdc_dir / "motions.html").exists()
        assert (slsdc_dir / "motions_statistics.html").exists()

        apiit_dir = DATA_DIR / "apiitisdc2026"
        assert (apiit_dir / "motions.html").exists()
        assert (apiit_dir / "motions_statistics.html").exists()
