"""
Tests for Atomos Phase 4 Analytical Engine.
"""

import sqlite3
from pathlib import Path
import pytest

from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.ratings import EloRatingEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.motions import MotionAnalytics
from atomos.analytics.engine import AnalyticsEngine


@pytest.fixture
def in_memory_analytics_db():
    """Create and seed an in-memory database with realistic debating data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    cur = conn.cursor()
    # Seed Institutions
    cur.execute("INSERT INTO institutions (id, name, code) VALUES (1, 'Royal College', 'RC')")
    cur.execute("INSERT INTO institutions (id, name, code) VALUES (2, 'S. Thomas College', 'STC')")

    # Seed Persons
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (1, 'Speaker A')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (2, 'Speaker B')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (3, 'Speaker C')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (4, 'Speaker D')")

    # Seed Tournaments
    cur.execute("INSERT INTO tournaments (id, slug, name, source_url) VALUES (1, 't1', 'Tournament 1', 'http://t1')")
    cur.execute("INSERT INTO tournaments (id, slug, name, source_url) VALUES (2, 't2', 'Tournament 2', 'http://t2')")

    # Seed Teams
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (1, 1, 'RC A', 1)")
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (2, 1, 'STC A', 2)")
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (3, 2, 'RC A', 1)")
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (4, 2, 'STC A', 2)")

    # Seed Rounds
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (1, 1, 1, 'Round 1', 'PRELIMINARY', 'This House would ban private schooling.')")
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (2, 1, 2, 'Round 2', 'PRELIMINARY', 'This House supports carbon taxation.')")
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (3, 1, 3, 'Round 3', 'PRELIMINARY', 'This House regrets social media.')")
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (4, 2, 1, 'Round 1', 'PRELIMINARY', 'This House would legalize organs.')")
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (5, 2, 2, 'Round 2', 'PRELIMINARY', 'This House supports AI regulation.')")
    cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type, motion) VALUES (6, 2, 3, 'Round 3', 'PRELIMINARY', 'This House would cancel debt.')")

    # Helper to insert a full debate with ballot and speeches
    def add_debate(deb_id, rnd_id, p_tid, o_tid, p_tot, o_tot, margin, winner, p_speaks, o_speaks):
        cur.execute("INSERT INTO debates (id, debate_id, round_id, prop_team_id, opp_team_id, is_walkover) VALUES (?, ?, ?, ?, ?, 0)",
                    (deb_id, str(deb_id), rnd_id, p_tid, o_tid))
        cur.execute("""
            INSERT INTO adjudicator_ballots (id, debate_id, prop_total_score, opp_total_score, win_margin, winner_side)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (deb_id, deb_id, p_tot, o_tot, margin, winner))

        # Proposition speeches
        pos = ["1st", "2nd", "3rd"]
        for i, (pid, score) in enumerate(p_speaks[:3]):
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, ?, 'Proposition', ?, 'SUBSTANTIVE', ?)
            """, (deb_id, deb_id, rnd_id, p_tid, pid, pos[i], score))
        if len(p_speaks) > 3:
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, ?, 'Proposition', 'Reply', 'REPLY', ?)
            """, (deb_id, deb_id, rnd_id, p_tid, p_speaks[3][0], p_speaks[3][1]))

        # Opposition speeches
        for i, (pid, score) in enumerate(o_speaks[:3]):
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, ?, 'Opposition', ?, 'SUBSTANTIVE', ?)
            """, (deb_id, deb_id, rnd_id, o_tid, pid, pos[i], score))
        if len(o_speaks) > 3:
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, ?, 'Opposition', 'Reply', 'REPLY', ?)
            """, (deb_id, deb_id, rnd_id, o_tid, o_speaks[3][0], o_speaks[3][1]))

    # Add 3 rounds in Tournament 1
    # Debate 1
    add_debate(
        1, 1, 1, 2, 252.0, 245.0, 7.0, 'Proposition',
        [(1, 73.0), (2, 72.0), (3, 71.0), (1, 36.0)],
        [(4, 70.0), (4, 70.0), (4, 70.0), (4, 35.0)]
    )
    # Debate 2
    add_debate(
        2, 2, 1, 2, 250.0, 246.0, 4.0, 'Proposition',
        [(1, 72.0), (2, 71.0), (3, 71.5), (2, 35.5)],
        [(4, 70.5), (4, 70.5), (4, 70.0), (4, 35.0)]
    )
    # Debate 3
    add_debate(
        3, 3, 1, 2, 254.0, 247.0, 7.0, 'Proposition',
        [(1, 74.0), (2, 72.5), (3, 71.5), (1, 36.0)],
        [(4, 70.5), (4, 70.5), (4, 71.0), (4, 35.0)]
    )

    # Add 3 rounds in Tournament 2
    add_debate(
        4, 4, 3, 4, 251.0, 248.0, 3.0, 'Proposition',
        [(1, 72.0), (2, 72.0), (3, 71.0), (1, 36.0)],
        [(4, 71.0), (4, 71.0), (4, 71.0), (4, 35.0)]
    )
    add_debate(
        5, 5, 3, 4, 253.0, 246.0, 7.0, 'Proposition',
        [(1, 73.0), (2, 72.5), (3, 71.5), (1, 36.0)],
        [(4, 70.0), (4, 70.5), (4, 70.5), (4, 35.0)]
    )
    add_debate(
        6, 6, 3, 4, 249.0, 250.0, -1.0, 'Opposition',
        [(1, 71.0), (2, 71.0), (3, 71.5), (2, 35.5)],
        [(4, 72.0), (4, 72.0), (4, 71.0), (4, 35.0)]
    )

    conn.commit()
    yield conn
    conn.close()


class TestMasterTabEngine:
    def test_master_speaker_tab_eligibility_and_calculation(self, in_memory_analytics_db):
        engine = MasterTabEngine(in_memory_analytics_db)
        tab = engine.get_master_speaker_tab(min_tournaments=1)

        assert len(tab) > 0
        top = tab[0]
        # Speaker 1 participated in 3 rounds in T1 (73, 72, 74 -> avg 73.0)
        # and 3 rounds in T2 (72, 73, 71 -> avg 72.0)
        # Master score (New Regulation) = (219 + 216) / 6 = 72.5
        # Legacy score = (73.0 + 72.0) / 2 = 72.5
        assert top["speaker_name"] == "Speaker A"
        assert top["eligible_tournaments"] == 2
        assert top["master_score"] == 72.5
        assert top["speech_average"] == 72.5
        assert top["avg_of_avgs"] == 72.5
        assert top["total_rounds"] == 6
        assert "national_level" in top

        # Test explicit legacy regulation
        legacy_tab = engine.get_master_speaker_tab(min_tournaments=1, regulation="legacy")
        assert legacy_tab[0]["master_score"] == 72.5
        assert legacy_tab[0]["regulation"] == "legacy"

    def test_master_reply_tab_calculation(self, in_memory_analytics_db):
        engine = MasterTabEngine(in_memory_analytics_db)
        rep_tab = engine.get_master_reply_tab(min_speeches=1)

        assert len(rep_tab) > 0
        # Speaker 1 delivered replies: 36.0, 36.0, 36.0, 36.0 -> avg 36.0
        s1 = next(r for r in rep_tab if r["speaker_name"] == "Speaker A")
        assert s1["reply_average"] == 36.0
        assert s1["reply_count"] == 4
        assert "national_level" in s1

    def test_master_team_tab_tiebreakers(self, in_memory_analytics_db):
        engine = MasterTabEngine(in_memory_analytics_db)
        team_tab = engine.get_master_team_tab(min_tournaments=1)

        assert len(team_tab) == 2
        # RC A won 5 of 6 debates
        assert team_tab[0]["team_name"] == "RC A"
        assert team_tab[0]["wins"] == 5
        assert team_tab[0]["debates_count"] == 6
        assert team_tab[0]["atss"] > 250.0


class TestEloRatingEngine:
    def test_elo_conservation_and_margin_scaling(self, in_memory_analytics_db):
        elo_engine = EloRatingEngine(in_memory_analytics_db)
        ratings = elo_engine.compute_team_ratings()

        rc = ratings["RC A"]
        stc = ratings["STC A"]

        # Winner of 5/6 debates should be rated significantly higher than 1500
        assert rc["rating"] > 1550.0
        assert stc["rating"] < 1450.0

        # Sum of ratings should be approximately conserved around 3000.0 (1500 * 2)
        total_elo = rc["rating"] + stc["rating"]
        assert pytest.approx(total_elo, abs=1.0) == 3000.0

    def test_debater_performance_index(self, in_memory_analytics_db):
        elo_engine = EloRatingEngine(in_memory_analytics_db)
        dpi_list = elo_engine.get_debater_performance_index(min_speeches=2)

        assert len(dpi_list) > 0
        # Speaker A consistently outperformed benchmark
        top_dpi = dpi_list[0]
        assert top_dpi["speaker_name"] == "Speaker A"
        assert top_dpi["dpi"] > 0.0


class TestInstitutionalAnalytics:
    def test_institution_power_index(self, in_memory_analytics_db):
        inst_engine = InstitutionAnalytics(in_memory_analytics_db)
        ipi_list = inst_engine.get_institutional_power_index()

        assert len(ipi_list) == 2
        # Royal College won 5/6 matches, should rank #1
        assert ipi_list[0]["name"] == "Royal College"
        assert ipi_list[0]["wins"] == 5
        assert ipi_list[0]["ipi"] > ipi_list[1]["ipi"]


class TestMotionAnalytics:
    def test_motion_balance_and_side_bias(self, in_memory_analytics_db):
        motion_engine = MotionAnalytics(in_memory_analytics_db)
        balance = motion_engine.get_overall_side_balance()

        assert balance["total_decisions"] == 6
        assert balance["prop_wins"] == 5
        assert balance["opp_wins"] == 1
        assert balance["prop_win_rate"] > 80.0


class TestAnalyticsEngineFacade:
    def test_executive_summary_structure(self, in_memory_analytics_db):
        engine = AnalyticsEngine(in_memory_analytics_db)
        summary = engine.get_executive_summary()

        assert summary["tournaments_count"] == 2
        assert summary["institutions_count"] == 2
        assert summary["debater_pool"] == 4
        assert summary["contested_debates"] == 6
        assert len(summary["top_speakers"]) > 0
        assert len(summary["top_teams"]) > 0
        assert len(summary["top_institutions"]) > 0
