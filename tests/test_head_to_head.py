"""
Unit tests for Atomos Head-to-Head Debater & Team Comparison Engine
"""

from pathlib import Path
import sqlite3
import pytest

from atomos.analytics.head_to_head import HeadToHeadEngine


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def setup_h2h_test_data(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Tournaments
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t1 = cur.lastrowid
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t2', 'Tournament 2', 'http://t2')")
    t2 = cur.lastrowid

    # Institutions
    cur.execute("INSERT INTO institutions (name, code) VALUES ('D. S. Senanayake College', 'DSSC')")
    inst_ds = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Royal College', 'RC')")
    inst_rc = cur.lastrowid
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Ananda College', 'AC')")
    inst_ac = cur.lastrowid

    # Persons
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Debater Alpha')")
    p_a = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Debater Beta')")
    p_b = cur.lastrowid

    # Teams
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'DS A', ?)", (t1, inst_ds))
    team_ds_t1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t1, inst_rc))
    team_rc_t1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AC A', ?)", (t1, inst_ac))
    team_ac_t1 = cur.lastrowid

    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'DS A', ?)", (t2, inst_ds))
    team_ds_t2 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t2, inst_rc))
    team_rc_t2 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'AC A', ?)", (t2, inst_ac))
    team_ac_t2 = cur.lastrowid

    # Members
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_ds_t1, p_a))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_ds_t2, p_a))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_rc_t1, p_b))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_rc_t2, p_b))

    # Rounds
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t1,))
    r1_t1 = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 2, 'Round 2', 'PRELIMINARY')", (t1,))
    r2_t1 = cur.lastrowid
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t2,))
    r1_t2 = cur.lastrowid

    # Adjudicator
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Adj 1')")
    adj_id = cur.lastrowid

    # Matchup 1 (t1 r1): Direct Clash between DS A (Prop) and RC A (Opp)
    # DS A wins 1-0 (+4 margin). Debater Alpha scores 74.0, Debater Beta scores 72.0.
    cur.execute(
        "INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_t1_r1', ?, ?)",
        (r1_t1, team_ds_t1, team_rc_t1),
    )
    d_direct = cur.lastrowid
    cur.execute(
        """
        INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin)
        VALUES (?, ?, 'Proposition', 222.0, 218.0, 4.0)
        """,
        (d_direct, adj_id),
    )
    b_direct = cur.lastrowid
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side)
        VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 74.0, 'Proposition')
        """,
        (b_direct, d_direct, r1_t1, team_ds_t1, p_a),
    )
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side)
        VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 72.0, 'Opposition')
        """,
        (b_direct, d_direct, r1_t1, team_rc_t1, p_b),
    )

    # Matchup 2 (t1 r2): DS A (Prop) vs AC A (Opp) - DS A wins 1-0 (+3 margin)
    cur.execute(
        "INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_t1_r2', ?, ?)",
        (r2_t1, team_ds_t1, team_ac_t1),
    )
    d_ds_ac = cur.lastrowid
    cur.execute(
        """
        INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin)
        VALUES (?, ?, 'Proposition', 220.0, 217.0, 3.0)
        """,
        (d_ds_ac, adj_id),
    )
    b_ds_ac = cur.lastrowid
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side)
        VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.0, 'Proposition')
        """,
        (b_ds_ac, d_ds_ac, r2_t1, team_ds_t1, p_a),
    )

    # Matchup 3 (t2 r1): RC A (Prop) vs AC A (Opp) - RC A wins 1-0 (+2 margin)
    cur.execute(
        "INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_t2_r1', ?, ?)",
        (r1_t2, team_rc_t2, team_ac_t2),
    )
    d_rc_ac = cur.lastrowid
    cur.execute(
        """
        INSERT INTO adjudicator_ballots (debate_id, adjudicator_person_id, winner_side, prop_total_score, opp_total_score, win_margin)
        VALUES (?, ?, 'Proposition', 221.0, 219.0, 2.0)
        """,
        (d_rc_ac, adj_id),
    )
    b_rc_ac = cur.lastrowid
    cur.execute(
        """
        INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, position, speech_type, total_score, side)
        VALUES (?, ?, ?, ?, ?, '1st', 'SUBSTANTIVE', 73.5, 'Proposition')
        """,
        (b_rc_ac, d_rc_ac, r1_t2, team_rc_t2, p_b),
    )

    conn.commit()
    return p_a, p_b


def test_debater_head_to_head(db_conn):
    p_a, p_b = setup_h2h_test_data(db_conn)
    engine = HeadToHeadEngine(db_conn)

    h2h = engine.compare_debaters(p_a, p_b)
    assert h2h is not None

    # Check debater profiles
    assert h2h.debater_a.canonical_name == "Debater Alpha"
    assert h2h.debater_b.canonical_name == "Debater Beta"

    # Check direct encounters
    assert len(h2h.direct_debates) == 1
    direct = h2h.direct_debates[0]
    assert direct.tournament_slug == "t1"
    assert direct.round_name == "Round 1"
    assert direct.team_a_name == "DS A"
    assert direct.team_b_name == "RC A"
    assert direct.side_a == "Proposition"
    assert direct.side_b == "Opposition"
    assert direct.a_won is True
    assert direct.b_won is False
    assert direct.margin_a == 4.0
    assert direct.sub_score_a == 74.0
    assert direct.sub_score_b == 72.0

    # Summary metrics
    assert h2h.a_direct_wins == 1
    assert h2h.b_direct_wins == 0
    assert h2h.a_direct_sub_avg == 74.0
    assert h2h.b_direct_sub_avg == 72.0

    # Common opponents (both faced AC A)
    assert len(h2h.common_opponents) == 1
    co = h2h.common_opponents[0]
    assert co.opponent_name == "AC A"
    assert co.opponent_institution == "Ananda College"
    assert co.a_debates == 1
    assert co.a_wins == 1
    assert co.a_win_pct == 100.0
    assert co.a_avg_margin == 3.0
    assert co.b_debates == 1
    assert co.b_wins == 1
    assert co.b_win_pct == 100.0
    assert co.b_avg_margin == 2.0


def test_debater_no_direct_clashes(db_conn):
    cur = db_conn.cursor()
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'T1', 'http://t1')")
    t1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Solo 1')")
    p1 = cur.lastrowid
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Solo 2')")
    p2 = cur.lastrowid

    engine = HeadToHeadEngine(db_conn)
    h2h = engine.compare_debaters(p1, p2)
    assert h2h is not None
    assert len(h2h.direct_debates) == 0
    assert h2h.a_direct_wins == 0
    assert h2h.b_direct_wins == 0
    assert h2h.a_direct_sub_avg is None
    assert h2h.b_direct_sub_avg is None
    assert len(h2h.common_opponents) == 0


def test_team_head_to_head(db_conn):
    setup_h2h_test_data(db_conn)
    engine = HeadToHeadEngine(db_conn)

    h2h = engine.compare_teams("DS A", "RC A")
    assert h2h is not None
    assert h2h.team_a_name == "DS A"
    assert h2h.team_b_name == "RC A"
    assert "D. S. Senanayake" in h2h.institution_a
    assert "Royal College" in h2h.institution_b

    # Direct encounters
    assert len(h2h.direct_debates) == 1
    d = h2h.direct_debates[0]
    assert d.a_won is True
    assert d.b_won is False
    assert d.margin_a == 4.0
    assert h2h.a_direct_wins == 1
    assert h2h.b_direct_wins == 0
    assert h2h.a_direct_margin_avg == 4.0
    assert h2h.b_direct_margin_avg == -4.0

    # Career metrics
    assert h2h.metrics_a["debates"] == 2
    assert h2h.metrics_a["wins"] == 2
    assert h2h.metrics_a["win_pct"] == 100.0

    # Common opponents
    assert len(h2h.common_opponents) == 1
    assert h2h.common_opponents[0].opponent_name == "AC A"
    assert h2h.common_opponents[0].a_wins == 1
    assert h2h.common_opponents[0].b_wins == 1
