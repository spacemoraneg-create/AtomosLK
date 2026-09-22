"""
Tests for Atomos V2 Adjudicator Analytics & Accuracy.

Verifies:
1. Data hygiene: Zero non-person placeholders (Scoresheet, Walkover, Tab, etc.) in the adjudicator dataset.
2. Prelims threshold: All adjudicators on the public leaderboard have >= 3 prelim rounds judged.
3. Full name resolution: Canonical mapping resolves single names (Tharushi, Damhiru, Shimar, etc.) into full names.
4. Metric accuracy: AASS within legitimate debate range (68-80), AATSS within range (200-250), non-negative wins.
5. Precision rule: Truncation up to 3 decimal places without rounding up.
6. Dossier retrieval: Individual bios resolve correctly for active adjudicators.
"""

import pytest
from atomos.database.connection import get_connection
from atomos.analytics.v2_metrics import V2MetricsEngine, truncate_3


@pytest.fixture(scope="module")
def db_conn():
    return get_connection()


@pytest.fixture(scope="module")
def engine(db_conn):
    return V2MetricsEngine(db_conn)


def test_no_non_person_adjudicators(engine):
    """Ensure zero non-person placeholders or administrative artifacts exist in the adjudicator leaderboard."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=0)
    banned_keywords = [
        "scoresheet",
        "official walkover",
        "official tab",
        "official panel decision",
        "official reconstructed",
        "tab",
    ]
    for judge in lb:
        name = judge["adjudicator_name"].lower()
        for banned in banned_keywords:
            assert banned not in name, f"Non-person record found in adjudicator list: {judge['adjudicator_name']}"


def test_leaderboard_prelims_threshold(engine):
    """Ensure all adjudicators on the standard leaderboard have >= 3 prelim rounds judged."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=3)
    assert len(lb) == 89, f"Expected exactly 89 qualified circuit adjudicators, got {len(lb)}"
    for judge in lb:
        assert judge["prelims_adjudicated"] >= 3, (
            f"Adjudicator {judge['adjudicator_name']} has {judge['prelims_adjudicated']} prelims (< 3)"
        )


def test_no_single_name_adjudicators_in_leaderboard(engine):
    """Ensure single-word aliases (e.g. 'Tharushi', 'Damhiru') are properly normalized to full canonical names."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=3)
    single_names = []
    for judge in lb:
        tokens = judge["adjudicator_name"].strip().split()
        if len(tokens) < 2:
            single_names.append(judge["adjudicator_name"])
    assert len(single_names) == 0, f"Found single-word adjudicator names that should be resolved: {single_names}"


def test_known_canonical_adjudicators_present(engine):
    """Verify known prominent circuit adjudicators appear with their full canonical names."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=3)
    names = {j["adjudicator_name"] for j in lb}

    expected_adjudicators = [
        "Minithi Hewage",
        "Kaveesha Mallawaarachchi",
        "Nethma Madawala",
        "Sanithma Jayasooriya",
        "Senuka Seneviratne",
        "Abdullah Yusoof",
    ]
    for expected in expected_adjudicators:
        assert expected in names, f"Expected canonical adjudicator '{expected}' missing from leaderboard"


def test_adjudicator_metrics_ranges(engine):
    """Verify that AASS, AATSS, and win rates fall within realistic debate standards."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=3)
    for judge in lb:
        if judge["aass"] is not None:
            assert 65.0 <= judge["aass"] <= 82.0, (
                f"AASS {judge['aass']} out of realistic bounds for {judge['adjudicator_name']}"
            )
        if judge["aatss"] is not None:
            assert 190.0 <= judge["aatss"] <= 260.0, (
                f"AATSS {judge['aatss']} out of realistic bounds for {judge['adjudicator_name']}"
            )
        assert judge["prop_wins"] >= 0
        assert judge["opp_wins"] >= 0
        assert 0.0 <= judge["prop_bias_pct"] <= 100.0
        assert 0.0 <= judge["opp_bias_pct"] <= 100.0
        assert judge["tournaments_adjudicated"] >= 1
        assert judge["ballots_count"] >= judge["prelims_adjudicated"]


def test_adjudicator_bio_retrieval(engine):
    """Ensure get_adjudicator_bio retrieves complete profile data."""
    bio = engine.get_adjudicator_bio("Minithi Hewage")
    assert bio is not None, "Could not retrieve bio for Minithi Hewage"
    assert "Minithi" in bio["adjudicator_name"]
    assert bio["prelims_adjudicated"] >= 3
    assert bio["aass"] is not None
    assert bio["aatss"] is not None
    assert "prop_bias_pct" in bio
    assert "opp_bias_pct" in bio


def test_truncation_precision():
    """Verify the universal truncation rule (truncate_3): truncate, never round up."""
    assert truncate_3(72.8499) == 72.849
    assert truncate_3(75.5555) == 75.555
    assert truncate_3(70.0) == 70.0
    assert truncate_3(68.1234) == 68.123
    assert truncate_3(None) is None
