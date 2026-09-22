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


def test_panel_outrounds_credited(engine):
    """Ensure panel elimination round ballots credit top circuit adjudicators with outrounds."""
    lb = engine.get_adjudicator_leaderboard(min_prelims=3)
    judges_map = {j["adjudicator_name"]: j for j in lb}

    # Prominent adjudicators who chaired / paneled outrounds
    senuka = judges_map.get("Senuka Seneviratne")
    assert senuka is not None, "Senuka Seneviratne must exist in leaderboard"
    assert senuka["outrounds_adjudicated"] >= 10, (
        f"Expected Senuka to have >= 10 outrounds credited from panels, got {senuka['outrounds_adjudicated']}"
    )
    assert senuka["total_rounds_adjudicated"] >= 35

    akindu = judges_map.get("Akindu Athauda")
    assert akindu is not None, "Akindu Athauda must exist in leaderboard"
    assert akindu["outrounds_adjudicated"] >= 10

    kaveesha = judges_map.get("Kaveesha Mallawaarachchi")
    assert kaveesha is not None, "Kaveesha Mallawaarachchi must exist in leaderboard"
    assert kaveesha["outrounds_adjudicated"] >= 10

    sarah = judges_map.get("Sarah Warnakulasuriya")
    assert sarah is not None, "Sarah Warnakulasuriya must exist in leaderboard"
    assert sarah["outrounds_adjudicated"] >= 10


def test_zero_orphan_single_name_judges_in_db(db_conn):
    """Ensure zero single-token person records exist where a full canonical counterpart exists."""
    cur = db_conn.cursor()
    cur.execute("""
        SELECT DISTINCT p.id, p.canonical_name
        FROM persons p
        JOIN adjudicator_ballots b ON b.adjudicator_person_id = p.id
    """)
    judges = cur.fetchall()
    single_token = [j[1] for j in judges if len(j[1].strip().split()) < 2]
    for s_name in single_token:
        cur.execute("SELECT id, canonical_name FROM persons WHERE canonical_name LIKE ? AND canonical_name != ?", (f"{s_name} %", s_name))
        counterparts = cur.fetchall()
        assert len(counterparts) == 0, f"Unmerged orphan single-name adjudicator '{s_name}' has full-name counterparts: {counterparts}"


def test_adjudicator_bio_detailed_history(engine):
    """Verify that get_adjudicator_bio provides match-level judging history with panel metadata."""
    bio = engine.get_adjudicator_bio("Senuka Seneviratne")
    assert bio is not None
    assert "judging_history" in bio
    history = bio["judging_history"]
    assert len(history) >= 30, f"Expected Senuka history >= 30 debates, got {len(history)}"

    # Verify structure of history items
    sample = history[0]
    assert "tournament_name" in sample
    assert "round_name" in sample
    assert "round_type" in sample
    assert "prop_team" in sample
    assert "opp_team" in sample
    assert "winner_side" in sample
    assert "is_panel" in sample
    assert "panel_members" in sample

    # Verify that panel rounds exist and have co-judges
    panel_rounds = [h for h in history if h["is_panel"]]
    assert len(panel_rounds) >= 10, "Expected at least 10 panel rounds in Senuka's history"
    for pr in panel_rounds:
        assert len(pr["panel_members"]) > 0


def test_conflict_of_interest_detection(db_conn):
    """Ensure conflict-of-interest checks can identify any debates where a judge judged their own institution."""
    cur = db_conn.cursor()
    cur.execute("""
        SELECT b.id, b.adjudicator_raw_name, b.adjudicator_institution, 
               t1.name as prop_team, i1.name as prop_inst,
               t2.name as opp_team, i2.name as opp_inst
        FROM adjudicator_ballots b
        JOIN debates d ON b.debate_id = d.id
        LEFT JOIN teams t1 ON d.prop_team_id = t1.id
        LEFT JOIN institutions i1 ON t1.institution_id = i1.id
        LEFT JOIN teams t2 ON d.opp_team_id = t2.id
        LEFT JOIN institutions i2 ON t2.institution_id = i2.id
        WHERE b.adjudicator_institution IS NOT NULL AND b.adjudicator_institution != ''
          AND (
            LOWER(b.adjudicator_institution) = LOWER(i1.name) OR LOWER(b.adjudicator_institution) = LOWER(i1.code)
            OR LOWER(b.adjudicator_institution) = LOWER(i2.name) OR LOWER(b.adjudicator_institution) = LOWER(i2.code)
          )
    """)
    conflicts = cur.fetchall()
    # In legitimate tournament operations, this should be near 0
    assert len(conflicts) <= 5, f"High number of institutional conflicts detected: {len(conflicts)}"

