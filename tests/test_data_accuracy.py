"""
Test Suite: Forensic Data Accuracy and System-Wide Invariants
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest

from atomos.database.connection import get_connection
from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.motions import MotionAnalytics
from atomos.analytics.head_to_head import HeadToHeadEngine


@pytest.fixture(scope="module")
def db_conn():
    conn = get_connection(Path("data/atomos.db"))
    yield conn
    conn.close()


def test_gate1_sqlite_integrity_check(db_conn):
    cur = db_conn.cursor()
    cur.execute("PRAGMA integrity_check")
    rows = cur.fetchall()
    assert len(rows) == 1 and rows[0][0] == "ok", f"Integrity check failed: {rows}"


def test_gate1_foreign_key_violations(db_conn):
    cur = db_conn.cursor()
    cur.execute("PRAGMA foreign_key_check")
    fk_violations = cur.fetchall()
    assert len(fk_violations) == 0, f"Foreign key violations found: {fk_violations}"


def test_gate1_orphan_records(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM speech_performances sp
        LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
        WHERE b.id IS NULL
    """)
    assert cur.fetchone()[0] == 0, "Found speech_performances with non-existent ballot_id"

    cur.execute("""
        SELECT COUNT(*) FROM adjudicator_ballots b
        LEFT JOIN debates d ON b.debate_id = d.id
        WHERE d.id IS NULL
    """)
    assert cur.fetchone()[0] == 0, "Found adjudicator_ballots with non-existent debate_id"


def test_gate2_zero_dual_side_debaters(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM speech_performances sp1
        JOIN speech_performances sp2 ON sp1.debate_id = sp2.debate_id AND sp1.person_id = sp2.person_id
        WHERE sp1.side = 'Proposition' AND sp2.side = 'Opposition'
    """)
    assert cur.fetchone()[0] == 0, "Found debaters speaking on both sides of the same debate"


def test_gate2_walkover_invariants(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM debates
        WHERE is_walkover = 1 
          AND (walkover_winner_id IS NULL OR walkover_winner_id NOT IN (prop_team_id, opp_team_id))
    """)
    assert cur.fetchone()[0] == 0, "Walkover debates with invalid winner found"

    cur.execute("""
        SELECT COUNT(*)
        FROM speech_performances sp
        JOIN debates d ON sp.debate_id = d.id
        WHERE d.is_walkover = 1 AND sp.total_score > 0
    """)
    assert cur.fetchone()[0] == 0, "Walkover debates should not have speech performances"


def test_gate3_wsdc_score_bounds(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM speech_performances
        WHERE speech_type = 'SUBSTANTIVE' AND total_score > 0
          AND (total_score < 60.0 OR total_score > 85.0)
    """)
    assert cur.fetchone()[0] == 0, "Substantive speeches out of WSDC bounds"

    cur.execute("""
        SELECT COUNT(*) FROM speech_performances
        WHERE speech_type = 'REPLY' AND total_score > 0
          AND (total_score < 30.0 OR total_score > 42.5)
    """)
    assert cur.fetchone()[0] == 0, "Reply speeches out of WSDC bounds"


def test_gate3_ballot_math_and_margins(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM adjudicator_ballots
        WHERE prop_total_score IS NOT NULL AND opp_total_score IS NOT NULL
          AND win_margin IS NOT NULL AND prop_total_score > 0 AND opp_total_score > 0
          AND ABS(ROUND(ABS(prop_total_score - opp_total_score), 2) - ABS(win_margin)) > 0.05
    """)
    assert cur.fetchone()[0] == 0, "Ballot win margins do not match |prop - opp|"

    cur.execute("""
        SELECT COUNT(*) FROM adjudicator_ballots
        WHERE prop_total_score IS NOT NULL AND opp_total_score IS NOT NULL
          AND ((prop_total_score > opp_total_score AND winner_side != 'Proposition')
               OR (opp_total_score > prop_total_score AND winner_side != 'Opposition'))
    """)
    assert cur.fetchone()[0] == 0, "Ballot winner contradicts higher score"


def test_gate4_master_audit_clean_pass():
    cmd = [sys.executable, "scripts/master_audit.py", "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["all_passed"] is True, f"Master audit failed: {report}"
    for g in report["gates"]:
        assert g["critical_errors_count"] == 0, f"Critical error in {g['gate']}: {g['critical_errors']}"


def test_gate5_master_tab_invariants(db_conn):
    engine = MasterTabEngine(db_conn)
    speakers = engine.get_master_speaker_tab(min_tournaments=2)
    assert len(speakers) > 0
    scores = [s["master_score"] for s in speakers]
    assert scores == sorted(scores, reverse=True), "Master speaker tab is not sorted descending"
    for s in speakers:
        assert 60.0 <= s["master_score"] <= 85.0, f"Invalid master score: {s}"


def test_gate5_institution_analytics_invariants(db_conn):
    analytics = InstitutionAnalytics(db_conn)
    ipi_list = analytics.get_institutional_power_index(min_debates=2)
    assert len(ipi_list) > 0
    ranks = [r["rank"] for r in ipi_list]
    assert ranks == list(range(1, len(ranks) + 1)), "IPI ranks are not contiguous"
    for r in ipi_list:
        assert 0.0 <= r["ipi"] <= 100.0, f"IPI score out of bounds: {r['ipi']}"


def test_gate5_cli_json_outputs():
    res1 = subprocess.run(
        [sys.executable, "scripts/view_identity.py", "Vidath Marasinghe", "--json", "--compact"],
        capture_output=True, text=True, check=True
    )
    d1 = json.loads(res1.stdout)
    assert d1["canonical_name"] == "Vidath Marasinghe"
    assert d1["master_tab_rank"] is not None

    res2 = subprocess.run(
        [sys.executable, "scripts/head_to_head.py", "Vidath Marasinghe", "Kaveesha De Silva", "--json"],
        capture_output=True, text=True, check=True
    )
    d2 = json.loads(res2.stdout)
    assert "debater_a" in d2 and "debater_b" in d2

    res3 = subprocess.run(
        [sys.executable, "scripts/compare_schools.py", "RC", "DS", "--json"],
        capture_output=True, text=True, check=True
    )
    d3 = json.loads(res3.stdout)
    assert d3["inst_a"]["code"] == "RC"
    assert d3["inst_b"]["code"] == "DS"

    res4 = subprocess.run(
        [sys.executable, "scripts/institutional_leaderboard.py", "--top", "5", "--json"],
        capture_output=True, text=True, check=True
    )
    d4 = json.loads(res4.stdout)
    assert len(d4) == 5
    assert d4[0]["rank"] == 1

    res5 = subprocess.run(
        [sys.executable, "scripts/circuit_report.py", "--top", "3", "--json"],
        capture_output=True, text=True, check=True
    )
    d5 = json.loads(res5.stdout)
    assert "high_level_stats" in d5
    assert "motions" in d5
    assert "institutions" in d5
    assert "debaters" in d5


def test_gate6_roster_sizes_and_rubric_integrity(db_conn):
    """Verify all teams adhere to WSDC roster size limits (3-5) and invalid rubric speeches have bounded total scores."""
    cur = db_conn.cursor()

    # 1. Roster sizes between 3 and 5 debaters
    cur.execute("""
        SELECT t.id, t.name, tour.slug, COUNT(tm.person_id) as sz
        FROM teams t
        JOIN tournaments tour ON t.tournament_id = tour.id
        JOIN team_members tm ON t.id = tm.team_id
        WHERE t.name NOT LIKE '%Swing%' AND t.name NOT LIKE '%BYE%'
        GROUP BY t.id
        HAVING sz < 3 OR sz > 5
    """)
    invalid_rosters = cur.fetchall()
    assert len(invalid_rosters) == 0, f"Found teams with invalid roster size: {invalid_rosters}"

    # 2. Speeches flagged is_valid_rubric=0 have valid WSDC total scores
    cur.execute("""
        SELECT COUNT(*) FROM speech_performances
        WHERE is_valid_rubric = 0
          AND (
            (speech_type = 'SUBSTANTIVE' AND (total_score < 60 OR total_score > 80))
            OR (speech_type = 'REPLY' AND (total_score < 30 OR total_score > 40))
          )
    """)
    unbounded_rubric_speeches = cur.fetchone()[0]
    assert unbounded_rubric_speeches == 0, f"Found non-standard rubric speeches with unbounded total scores: {unbounded_rubric_speeches}"