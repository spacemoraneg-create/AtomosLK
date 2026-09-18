"""
Unit tests for Atomos Debater Profile Engine
"""

from pathlib import Path
import sqlite3
import pytest

from atomos.analytics.debater_profile import DebaterProfileEngine


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    yield conn
    conn.close()


def setup_profile_test_data(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Tournaments
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t1', 'Tournament 1', 'http://t1')")
    t1 = cur.lastrowid
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t2', 'Tournament 2', 'http://t2')")
    t2 = cur.lastrowid
    cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t3', 'Tournament 3', 'http://t3')")
    t3 = cur.lastrowid

    # Institution
    cur.execute("INSERT INTO institutions (name, code) VALUES ('Royal College', 'RC')")
    inst_id = cur.lastrowid

    # Person
    cur.execute("INSERT INTO persons (canonical_name) VALUES ('Dithira De Silva')")
    p_id = cur.lastrowid

    # Alias
    cur.execute("INSERT INTO person_aliases (person_id, raw_name) VALUES (?, 'Dithira de Silva')", (p_id,))

    # Teams
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t1, inst_id))
    team1 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t2, inst_id))
    team2 = cur.lastrowid
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'RC A', ?)", (t3, inst_id))
    team3 = cur.lastrowid

    # Team members
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team1, p_id))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team2, p_id))
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team3, p_id))

    # Opponent team
    cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Opp Team', ?)", (t1, inst_id))
    opp1 = cur.lastrowid

    # T1: 3 prelim rounds (Scores: 72.0, 73.0, 74.0 -> Avg = 73.0)
    for r_num, score in [(1, 72.0), (2, 73.0), (3, 74.0)]:
        cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, ?, ?, 'PRELIMINARY')", (t1, r_num, f"Round {r_num}"))
        r_id = cur.lastrowid
        cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, ?, ?, ?)", (r_id, f"d_t1_{r_num}", team1, opp1))
        d_id = cur.lastrowid
        cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side) VALUES (?, 220, 215, 'Proposition')", (d_id,))
        b_id = cur.lastrowid
        cur.execute(
            "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', ?)",
            (b_id, d_id, r_id, team1, p_id, score),
        )

    # T2: 3 prelim rounds (Scores: 70.0, 72.0, 71.0 -> Avg = 71.0)
    for r_num, score in [(1, 70.0), (2, 72.0), (3, 71.0)]:
        cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, ?, ?, 'PRELIMINARY')", (t2, r_num, f"Round {r_num}"))
        r_id = cur.lastrowid
        cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, ?, ?, ?)", (r_id, f"d_t2_{r_num}", team2, opp1))
        d_id = cur.lastrowid
        cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side) VALUES (?, 210, 215, 'Opposition')", (d_id,))
        b_id = cur.lastrowid
        cur.execute(
            "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', ?)",
            (b_id, d_id, r_id, team2, p_id, score),
        )

    # T3: 1 prelim round (Score: 75.0 -> Ineligible, < 3 rounds)
    cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t3,))
    r_id = cur.lastrowid
    cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_t3_1', ?, ?)", (r_id, team3, opp1))
    d_id = cur.lastrowid
    cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side) VALUES (?, 225, 220, 'Proposition')", (d_id,))
    b_id = cur.lastrowid
    cur.execute(
        "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '1st', 'SUBSTANTIVE', 75.0)",
        (b_id, d_id, r_id, team3, p_id),
    )

    conn.commit()
    return p_id


class TestDebaterProfileEngine:

    def test_search_debaters(self, db_conn):
        p_id = setup_profile_test_data(db_conn)
        engine = DebaterProfileEngine(db_conn)

        # By full name
        res1 = engine.search_debaters("Dithira De Silva")
        assert len(res1) == 1
        assert res1[0].person_id == p_id
        assert res1[0].canonical_name == "Dithira De Silva"

        # By alias
        res2 = engine.search_debaters("Dithira de Silva")
        assert len(res2) == 1
        assert res2[0].person_id == p_id

        # By partial name
        res3 = engine.search_debaters("Dithira")
        assert len(res3) == 1
        assert res3[0].person_id == p_id

        # By ID
        res4 = engine.search_debaters(str(p_id))
        assert len(res4) == 1
        assert res4[0].person_id == p_id

    def test_get_profile_complete_dossier(self, db_conn):
        p_id = setup_profile_test_data(db_conn)
        engine = DebaterProfileEngine(db_conn)

        prof = engine.get_profile(p_id)
        assert prof is not None

        # Basic identity
        assert prof.canonical_name == "Dithira De Silva"
        assert prof.institution == "Royal College"
        assert "Dithira de Silva" in prof.aliases
        assert "RC A" in prof.teams_debated

        # Tournaments & Eligibility:
        # T1 has 3 rounds (eligible, avg 73.0)
        # T2 has 3 rounds (eligible, avg 71.0)
        # T3 has 1 round (ineligible, < 3 rounds)
        # Qualifying tournaments = 2 (T1, T2)
        assert prof.eligible_tournaments_count == 2
        assert prof.total_tournaments_count == 3
        assert prof.prelim_rounds_debated == 6  # 3 + 3 eligible rounds

        # Overall Average (New Regulation Priority): (219 + 213) / 6 = 72.0
        assert prof.overall_substantive_avg == 72.0
        assert prof.speech_average == 72.0
        assert prof.avg_of_avgs == 72.0

        # Raw Average: (72 + 73 + 74 + 70 + 72 + 71 + 75) / 7 = 507 / 7 = 72.42857
        assert prof.raw_substantive_avg == 72.42857

        # Derivation text checks
        assert "WSDC & Atomos Master Tab Standardization Rules" in prof.derivation_text
        assert "Overall Avg = (Sum of Qualifying Tournament Averages) / (Total Qualifying Tournaments)" in prof.derivation_text
        assert "73" in prof.derivation_text
        assert "71" in prof.derivation_text
        assert "72 pts" in prof.derivation_text

    def test_get_profile_non_existent_returns_none(self, db_conn):
        engine = DebaterProfileEngine(db_conn)
        prof = engine.get_profile(99999)
        assert prof is None

    def test_paneled_debate_score_averaging(self, db_conn):
        cur = db_conn.cursor()
        cur.execute("INSERT INTO tournaments (slug, name, source_url) VALUES ('t_panel', 'Panel Tournament', 'http://tp')")
        t_id = cur.lastrowid
        cur.execute("INSERT INTO institutions (name, code) VALUES ('Panel School', 'PS')")
        inst_id = cur.lastrowid
        cur.execute("INSERT INTO persons (canonical_name) VALUES ('Paneled Debater')")
        p_id = cur.lastrowid
        cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Panel Team', ?)", (t_id, inst_id))
        team_id = cur.lastrowid
        cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (?, ?)", (team_id, p_id))
        cur.execute("INSERT INTO teams (tournament_id, name, institution_id) VALUES (?, 'Opp Team', ?)", (t_id, inst_id))
        opp_id = cur.lastrowid

        # Round 1 has a 2-judge panel: Judge A gives 70.5, Judge B gives 71.5 -> Avg must be 71.0
        cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, 1, 'Round 1', 'PRELIMINARY')", (t_id,))
        r1_id = cur.lastrowid
        cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, 'd_p_1', ?, ?)", (r1_id, team_id, opp_id))
        d1_id = cur.lastrowid
        cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side, adjudicator_raw_name) VALUES (?, 215, 210, 'Proposition', 'Judge A')", (d1_id,))
        b1_id = cur.lastrowid
        cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side, adjudicator_raw_name) VALUES (?, 216, 210, 'Proposition', 'Judge B')", (d1_id,))
        b2_id = cur.lastrowid

        cur.execute(
            "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '2nd', 'SUBSTANTIVE', 70.5)",
            (b1_id, d1_id, r1_id, team_id, p_id),
        )
        cur.execute(
            "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '2nd', 'SUBSTANTIVE', 71.5)",
            (b2_id, d1_id, r1_id, team_id, p_id),
        )

        # Add rounds 2 and 3 so tournament is eligible
        for r_num, sc in [(2, 72.0), (3, 73.0)]:
            cur.execute("INSERT INTO rounds (tournament_id, round_number, name, round_type) VALUES (?, ?, ?, 'PRELIMINARY')", (t_id, r_num, f"Round {r_num}"))
            r_id = cur.lastrowid
            cur.execute("INSERT INTO debates (round_id, debate_id, prop_team_id, opp_team_id) VALUES (?, ?, ?, ?)", (r_id, f"d_p_{r_num}", team_id, opp_id))
            d_id = cur.lastrowid
            cur.execute("INSERT INTO adjudicator_ballots (debate_id, prop_total_score, opp_total_score, winner_side, adjudicator_raw_name) VALUES (?, 215, 210, 'Proposition', 'Solo Judge')", (d_id,))
            b_id = cur.lastrowid
            cur.execute(
                "INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score) VALUES (?, ?, ?, ?, ?, 'Proposition', '2nd', 'SUBSTANTIVE', ?)",
                (b_id, d_id, r_id, team_id, p_id, sc),
            )

        db_conn.commit()

        engine = DebaterProfileEngine(db_conn)
        prof = engine.get_profile(p_id)
        assert prof is not None
        assert len(prof.tournaments) == 1
        t = prof.tournaments[0]

        # Round 1 substantive score MUST be exactly 71.0 (mean of 70.5 and 71.5), NOT 71.5
        r1 = t.prelim_rounds[0]
        assert r1.substantive_score == 71.0
        assert len(r1.speeches) == 2
        assert r1.speeches[0].judge_name == "Judge A"
        assert r1.speeches[1].judge_name == "Judge B"

        # Tournament average: (71.0 + 72.0 + 73.0) / 3 = 72.00
        assert t.prelim_substantive_scores == [71.0, 72.0, 73.0]
        assert t.tournament_average == 72.00


def test_profile_national_level(db_conn):
    cur = db_conn.cursor()
    cur.execute("INSERT INTO persons (canonical_name, national_level) VALUES (?, ?)", ("Test Debater", "Nat Pool, Direct"))
    p_id = cur.lastrowid

    engine = DebaterProfileEngine(db_conn)
    prof = engine.get_profile(p_id)
    assert prof is not None
    assert prof.national_level == "Nat Pool, Direct"

    # Search
    results = engine.search_debaters("Test Debater")
    assert len(results) == 1
    assert results[0].national_level == "Nat Pool, Direct"

