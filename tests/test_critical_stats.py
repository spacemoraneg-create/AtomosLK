"""
Tests for Atomos Critical Stats Engine.
"""

import sqlite3
from pathlib import Path
import pytest

from atomos.analytics.critical_stats import CriticalStatsEngine


@pytest.fixture
def seeded_critical_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    cur = conn.cursor()
    cur.execute("INSERT INTO institutions (id, name, code) VALUES (1, 'Royal College', 'RC')")
    cur.execute("INSERT INTO institutions (id, name, code) VALUES (2, 'Ananda College', 'AC')")

    # Persons
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (1, 'Debater MultiTour')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (2, 'Debater OneTour')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (3, 'Debater Opp')")

    # Tournaments (3 distinct tournaments)
    for t_id in range(1, 4):
        cur.execute("INSERT INTO tournaments (id, slug, name, source_url) VALUES (?, ?, ?, ?)",
                    (t_id, f"t{t_id}", f"Tournament {t_id}", f"http://t{t_id}"))

        # Teams in each tournament
        cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (?, ?, 'RC A', 1)",
                    (t_id * 10 + 1, t_id))
        cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (?, ?, 'AC A', 2)",
                    (t_id * 10 + 2, t_id))

        # Rounds in each tournament: 3 prelims + 1 elimination
        for r_num in range(1, 4):
            r_id = t_id * 10 + r_num
            cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type) VALUES (?, ?, ?, ?, 'PRELIMINARY')",
                        (r_id, t_id, r_num, f"Round {r_num}"))
            
            # Debate
            deb_id = r_id
            p_tid = t_id * 10 + 1
            o_tid = t_id * 10 + 2
            cur.execute("INSERT INTO debates (id, debate_id, round_id, prop_team_id, opp_team_id, is_walkover) VALUES (?, ?, ?, ?, ?, 0)",
                        (deb_id, str(deb_id), r_id, p_tid, o_tid))
            cur.execute("""
                INSERT INTO adjudicator_ballots (id, debate_id, prop_total_score, opp_total_score, win_margin, winner_side)
                VALUES (?, ?, 250.0, 245.0, 5.0, 'Proposition')
            """, (deb_id, deb_id))

            # Speeches: Debater 1 speaks for Prop in all 3 tournaments
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, 1, 'Proposition', '1st', 'SUBSTANTIVE', 72.0)
            """, (deb_id, deb_id, r_id, p_tid))
            cur.execute("""
                INSERT INTO speech_performances (ballot_id, debate_id, round_id, team_id, person_id, side, position, speech_type, total_score)
                VALUES (?, ?, ?, ?, 3, 'Opposition', '1st', 'SUBSTANTIVE', 70.0)
            """, (deb_id, deb_id, r_id, o_tid))

        # Round 4: Elimination (Break round)
        elim_rid = t_id * 10 + 4
        cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type) VALUES (?, ?, 4, 'Final', 'ELIMINATION')",
                    (elim_rid, t_id))
        elim_did = elim_rid
        cur.execute("INSERT INTO debates (id, debate_id, round_id, prop_team_id, opp_team_id, is_walkover) VALUES (?, ?, ?, ?, ?, 0)",
                    (elim_did, str(elim_did), elim_rid, t_id * 10 + 1, t_id * 10 + 2))
        cur.execute("""
            INSERT INTO adjudicator_ballots (id, debate_id, prop_total_score, opp_total_score, win_margin, winner_side)
            VALUES (?, ?, NULL, NULL, NULL, 'Proposition')
        """, (elim_did, elim_did))

    conn.commit()
    yield conn
    conn.close()


class TestCriticalStatsEngine:
    def test_debater_critical_stats_eligibility_and_metrics(self, seeded_critical_db):
        engine = CriticalStatsEngine(seeded_critical_db)
        debaters = engine.get_critical_speaker_stats(min_tournaments=3)

        # Both Debater 1 (Prop) and Debater 3 (Opp) participated in 3 tournaments (9 prelims each)
        assert len(debaters) == 2
        d1 = debaters[0]
        assert d1["speaker_name"] == "Debater MultiTour"
        assert d1["eligible_tournaments"] == 3
        assert d1["prelim_rounds_debated"] == 9
        assert d1["avg"] == 72.0
        assert d1["speech_avg"] == 72.0
        assert d1["avg_of_avgs"] == 72.0
        # Consistently scored 72.0, so within-tournament deviation should be 0.0
        assert d1["avg_of_deviations"] == 0.0
        # Prop won all prelims
        assert d1["win_rate_debated"] == 100.0
        # RC A reached elimination round in all 3 tournaments -> 100.0% break
        assert d1["break_percentage"] == 100.0
        assert "national_level" in d1

        # Verify explicit legacy regulation
        legacy_debaters = engine.get_critical_speaker_stats(min_tournaments=3, regulation="legacy")
        assert legacy_debaters[0]["avg"] == 72.0
        assert legacy_debaters[0]["regulation"] == "legacy"

    def test_debater_excluded_if_under_tournament_threshold(self, seeded_critical_db):
        engine = CriticalStatsEngine(seeded_critical_db)
        # Requiring 4 tournaments should yield 0 debaters
        debaters_4 = engine.get_critical_speaker_stats(min_tournaments=4)
        assert len(debaters_4) == 0

    def test_team_critical_stats_metrics(self, seeded_critical_db):
        engine = CriticalStatsEngine(seeded_critical_db)
        teams = engine.get_critical_team_stats(min_tournaments=3)

        assert len(teams) == 2
        rc = next(t for t in teams if t["team_name"] == "RC A")
        assert rc["tournaments_count"] == 3
        # 3 prelims + 1 elimination per tournament = 12 rounds total
        assert rc["rounds_debated"] == 12
        # 1 elimination round per tournament = 3 break rounds
        assert rc["break_rounds_debated"] == 3
        # Broke in all 3 tournaments
        assert rc["break_percentage"] == 100.0
        # Won all 12 matches
        assert rc["win_percentage"] == 100.0
        # All debates were Proposition
        assert rc["opp_prop_split"]["prop_win_percentage"] == 100.0
        assert rc["atss"] == 250.0
        assert rc["avg_margins"] == 5.0

    def test_walkover_wins_counted_without_contaminating_atss(self, seeded_critical_db):
        conn = seeded_critical_db
        cur = conn.cursor()
        # Add a walkover prelim debate to tournament 1
        cur.execute("INSERT INTO rounds (id, tournament_id, round_number, name, round_type) VALUES (199, 1, 5, 'Round 5', 'PRELIMINARY')")
        cur.execute("INSERT INTO debates (id, debate_id, round_id, prop_team_id, opp_team_id, is_walkover) VALUES (199, '199', 199, 11, 12, 1)")
        cur.execute("""
            INSERT INTO adjudicator_ballots (id, debate_id, prop_total_score, opp_total_score, win_margin, winner_side)
            VALUES (199, 199, NULL, NULL, NULL, 'Proposition')
        """)
        conn.commit()

        engine = CriticalStatsEngine(conn)
        teams = engine.get_critical_team_stats(min_tournaments=3)
        rc = next(t for t in teams if t["team_name"] == "RC A")

        # 12 original rounds + 1 walkover = 13 rounds
        assert rc["rounds_debated"] == 13
        # Won all 13 matches (12 scored + 1 walkover win)
        assert rc["win_percentage"] == 100.0
        # ATSS must remain exactly 250.0 (uncontaminated by the walkover)
        assert rc["atss"] == 250.0
        # Avg winning margin must remain exactly 5.0
        assert rc["avg_margins"] == 5.0

    def test_team_highest_achievement_and_margins(self, seeded_critical_db):
        engine = CriticalStatsEngine(seeded_critical_db)
        
        # Test min_tournaments=1 (Master Tab: includes all teams)
        master_teams = engine.get_critical_team_stats(min_tournaments=1)
        assert len(master_teams) == 2
        
        # Test min_tournaments=4 (Critical Tab threshold: excludes teams with < 4 tournaments)
        crit_teams_4 = engine.get_critical_team_stats(min_tournaments=4)
        assert len(crit_teams_4) == 0
        
        # Check RC A highest achievement and margin details
        rc = next(t for t in master_teams if t["team_name"] == "RC A")
        assert rc["highest_achievement"] == "Champion"
        assert rc["highest_break"] == "Champion"
        assert rc["avg_win_margin"] == 5.0
        assert rc["tournaments_debated"] == 3
        assert "net_margin" in rc
        assert "avg_loss_margin" in rc

        # Check AC A
        ac = next(t for t in master_teams if t["team_name"] == "AC A")
        assert ac["highest_achievement"] == "Finalist"
        assert ac["avg_loss_margin"] == 5.0

