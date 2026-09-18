"""
Unit tests for Atomos Institutional Analytics & Leaderboard Engine
"""

from pathlib import Path
import sqlite3
import pytest

from atomos.analytics.institutions import InstitutionAnalytics


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def setup_inst_test_data(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Tournaments
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t1 = cur.lastrowid
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t2', 'Tournament 2', 'http://t2')")
    t2 = cur.lastrowid

    # Institutions
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Royal College', 'RC')")
    inst_rc = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('D. S. Senanayake College', 'DS')")
    inst_ds = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Ananda College', 'AC')")
    inst_ac = cur.lastrowid

    # Debaters
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('RC Debater')")
    p_rc = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('DS Debater')")
    p_ds = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('AC Debater')")
    p_ac = cur.lastrowid

    # Teams
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t1, inst_rc))
    team_rc1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'DS A', ?)", (t1, inst_ds))
    team_ds1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AC A', ?)", (t1, inst_ac))
    team_ac1 = cur.lastrowid

    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t2, inst_rc))
    team_rc2 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'DS A', ?)", (t2, inst_ds))
    team_ds2 = cur.lastrowid

    # Team members
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_rc1, p_rc))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_rc2, p_rc))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_ds1, p_ds))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_ds2, p_ds))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_ac1, p_ac))

    # Rounds
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t1,))
    r1_t1 = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 2, 'Round 2', 'PRELIMINARY')", (t1,))
    r2_t1 = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 3, 'Grand Finals', 'ELIMINATION')", (t1,))
    r3_t1 = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t2,))
    r1_t2 = cur.lastrowid

    # Adjudicator
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Judge 1')")
    adj_id = cur.lastrowid

    # Debate 1 (t1 r1): RC A (Prop) vs DS A (Opp) -> RC A wins 1-0 (+4 margin)
    cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd1', ?, ?)", (r1_t1, team_rc1, team_ds1))
    d1 = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin) VALUES (?, ?, 'Proposition', 224.0, 220.0, 4.0)", (d1, adj_id))
    b1 = cur.lastrowid
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 75.0, 'Proposition')", (b1, d1, r1_t1, team_rc1, p_rc))
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.0, 'Opposition')", (b1, d1, r1_t1, team_ds1, p_ds))

    # Debate 2 (t1 r2): DS A (Prop) vs AC A (Opp) -> DS A wins 1-0 (+2 margin)
    cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd2', ?, ?)", (r2_t1, team_ds1, team_ac1))
    d2 = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin) VALUES (?, ?, 'Proposition', 222.0, 220.0, 2.0)", (d2, adj_id))
    b2 = cur.lastrowid
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 74.0, 'Proposition')", (b2, d2, r2_t1, team_ds1, p_ds))
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.0, 'Opposition')", (b2, d2, r2_t1, team_ac1, p_ac))

    # Debate 3 (t1 r3 Elimination): RC A (Prop) vs DS A (Opp) -> DS A wins 1-0 (+3 margin)
    cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd3', ?, ?)", (r3_t1, team_rc1, team_ds1))
    d3 = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin) VALUES (?, ?, 'Opposition', 220.0, 223.0, -3.0)", (d3, adj_id))
    b3 = cur.lastrowid
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.0, 'Proposition')", (b3, d3, r3_t1, team_rc1, p_rc))
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 75.0, 'Opposition')", (b3, d3, r3_t1, team_ds1, p_ds))

    # Debate 4 (t2 r1): RC A (Prop) vs DS A (Opp) -> RC A wins 1-0 (+1 margin)
    cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd4', ?, ?)", (r1_t2, team_rc2, team_ds2))
    d4 = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin) VALUES (?, ?, 'Proposition', 221.0, 220.0, 1.0)", (d4, adj_id))
    b4 = cur.lastrowid
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 74.0, 'Proposition')", (b4, d4, r1_t2, team_rc2, p_rc))
    cur.execute("INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side) VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.5, 'Opposition')", (b4, d4, r1_t2, team_ds2, p_ds))

    conn.commit()
    return inst_rc, inst_ds, inst_ac


def test_institutional_power_index_calculation(db_conn):
    setup_inst_test_data(db_conn)
    analytics = InstitutionAnalytics(db_conn)
    ipi = analytics.get_institutional_power_index(min_debates=1)

    assert len(ipi) >= 2
    rc_data = next((r for r in ipi if r["name"] == "Royal College"), None)
    ds_data = next((r for r in ipi if r["name"] == "D. S. Senanayake College"), None)

    assert rc_data is not None
    assert ds_data is not None
    assert rc_data["wins"] == 2
    assert rc_data["total_debates"] == 3
    assert ds_data["wins"] == 2
    assert ds_data["total_debates"] == 4
    assert ds_data["elim_wins"] == 1
    assert rc_data["rank"] in (1, 2)


def test_institution_profile(db_conn):
    inst_rc, inst_ds, _ = setup_inst_test_data(db_conn)
    analytics = InstitutionAnalytics(db_conn)

    prof = analytics.get_institution_profile(inst_rc)
    assert prof is not None
    assert prof.name == "Royal College"
    assert prof.code == "RC"
    assert prof.total_debates == 3
    assert prof.wins == 2
    assert prof.losses == 1
    assert prof.win_rate == pytest.approx(66.7, rel=1e-1)
    assert prof.tournaments_entered == 2
    assert prof.debater_count == 1
    assert "RC A" in prof.teams_fielded
    assert len(prof.campaigns) == 2
    assert len(prof.rivalries) >= 1

    # Lookup by name and code
    prof_by_name = analytics.get_institution_profile("Royal College")
    assert prof_by_name.institution_id == inst_rc
    prof_by_code = analytics.get_institution_profile("RC")
    assert prof_by_code.institution_id == inst_rc


def test_compare_institutions(db_conn):
    inst_rc, inst_ds, _ = setup_inst_test_data(db_conn)
    analytics = InstitutionAnalytics(db_conn)

    cmp = analytics.compare_institutions(inst_rc, inst_ds)
    assert cmp is not None
    assert cmp.inst_a.name == "Royal College"
    assert cmp.inst_b.name == "D. S. Senanayake College"
    assert len(cmp.direct_debates) == 3

    # RC won d1 and d4, DS won d3
    assert cmp.a_direct_wins == 2
    assert cmp.b_direct_wins == 1
    assert cmp.a_direct_margin_avg is not None
    assert cmp.b_direct_margin_avg == -cmp.a_direct_margin_avg


def test_institution_not_found(db_conn):
    analytics = InstitutionAnalytics(db_conn)
    assert analytics.get_institution_profile(9999) is None
    assert analytics.get_institution_profile("NonExistentSchool") is None
