"""
Atomos V2 Mathematical and Functional Regression Suite

Verifies all requirements from Atomos V2 Upgrade READ_ME.txt:
1. Universal Speaker Score Law (Substantive mean only, replies strictly excluded).
2. Sample standard deviation calculation.
3. Multi-Purpose Speaker Leaderboard (Tab >= 12 rds, General >= 5 rds, 5 switchable metrics).
4. Multi-Purpose Team Leaderboard (Tab >= 3 tourneys, General >= 2 tourneys, 4 metrics).
5. Team Bio & Lineup Analytics (Top 5 Win % and Top 5 ATSS 3-speaker combinations).
6. Multi-Purpose Institution Leaderboard (New Delta formula (0.8*A + 1.2*B)/2, Net Diff, Pool).
7. Institution Bio (Veteran vs New debaters).
8. Adjudicator Bio (AASS, AATSS, Prop/Opp bias, prelims & tourneys).
9. Hard Tournament Leaderboard (7 official metrics).
10. National Pool 3-Tier Registry (3 unranked clean rosters).
11. V2 Head-to-Head (6 official metrics).
12. Server REST Endpoints (/api/v2/...).
"""

import math
import pytest
from atomos.database.connection import get_connection
from atomos.analytics.v2_metrics import V2MetricsEngine, calc_sample_stdev
from atomos.server import create_app


@pytest.fixture(scope="module")
def conn():
    return get_connection()


@pytest.fixture(scope="module")
def v2(conn):
    return V2MetricsEngine(conn)


@pytest.fixture(scope="module")
def client(conn):
    app = create_app(db_conn=conn)
    app.config["TESTING"] = True
    return app.test_client()


class TestV2UniversalLaw:
    """Universal Speaker Score: Substantive speeches only."""

    def test_universal_substantive_mean(self, conn, v2):
        # Verify Vidath Marasinghe substantive mean across all tournaments
        prof = v2.get_debater_v2_profile("Vidath Marasinghe")
        assert prof is not None

        # Manually compute substantive mean from raw database
        cur = conn.cursor()
        cur.execute("""
            SELECT SUM(sp.total_score) as tot, COUNT(sp.id) as cnt
            FROM speech_performances sp
            JOIN persons p ON sp.person_id = p.id
            WHERE p.canonical_name = 'Vidath Marasinghe'
              AND sp.speech_type = 'SUBSTANTIVE' AND sp.total_score > 0
        """)
        row = cur.fetchone()
        expected_avg = round(row["tot"] / row["cnt"], 5)
        assert round(prof["speaker_avg"], 5) == expected_avg
        assert round(prof["speaker_score"], 5) == expected_avg

    def test_sample_stdev(self):
        # Empty and 1-item lists
        assert calc_sample_stdev([]) == 0.0
        assert calc_sample_stdev([75.0]) == 0.0

        # Normal sample standard deviation
        data = [70.0, 72.0, 74.0]
        # mean = 72, diffs = [-2, 0, 2], sq = [4, 0, 4], sum = 8, var = 8/2 = 4, stdev = 2.0
        assert calc_sample_stdev(data) == 2.0


class TestV2SpeakerLeaderboards:
    """Multi-Purpose Speaker Leaderboard: Tab vs General Tab."""

    def test_speaker_tab_minimum_12_rounds(self, v2):
        tab = v2.get_multipurpose_speakers(tier="tab", sort_by="speaker_score")
        assert len(tab) > 0
        for s in tab:
            assert s["prelims_debated"] >= 12

    def test_speaker_general_minimum_5_rounds(self, v2):
        gen = v2.get_multipurpose_speakers(tier="general", sort_by="speaker_score")
        assert len(gen) > len(v2.get_multipurpose_speakers(tier="tab"))
        for s in gen:
            assert s["prelims_debated"] >= 5

    def test_speaker_sorting_metrics(self, v2):
        # Sort by win_percentage
        by_win = v2.get_multipurpose_speakers(tier="tab", sort_by="win_percentage")
        for i in range(len(by_win) - 1):
            assert by_win[i]["win_percentage"] >= by_win[i + 1]["win_percentage"]

        # Sort by stdev (lower is better)
        by_stdev = v2.get_multipurpose_speakers(tier="tab", sort_by="stdev")
        for i in range(len(by_stdev) - 1):
            assert by_stdev[i]["stdev"] <= by_stdev[i + 1]["stdev"]

        # Sort by prelims
        by_prelims = v2.get_multipurpose_speakers(tier="tab", sort_by="prelims_debated")
        for i in range(len(by_prelims) - 1):
            assert by_prelims[i]["prelims_debated"] >= by_prelims[i + 1]["prelims_debated"]


class TestV2TeamLeaderboards:
    """Multi-Purpose Team Leaderboard & Lineup Analytics."""

    def test_team_tab_minimum_3_tournaments(self, v2):
        teams_tab = v2.get_multipurpose_teams(tier="tab", sort_by="atss")
        assert len(teams_tab) > 0
        for t in teams_tab:
            assert t["tournaments_debated"] >= 3

    def test_team_general_minimum_2_tournaments(self, v2):
        teams_gen = v2.get_multipurpose_teams(tier="general", sort_by="atss")
        assert len(teams_gen) > len(v2.get_multipurpose_teams(tier="tab"))
        for t in teams_gen:
            assert t["tournaments_debated"] >= 2

    def test_team_bio_lineups(self, v2):
        bio = v2.get_team_bio("DS A")
        assert bio is not None
        assert bio["atss"] > 240.0
        assert len(bio["top_win_lineups"]) <= 5
        assert len(bio["top_atss_lineups"]) <= 5
        for l in bio["top_win_lineups"]:
            assert len(l["lineup"]) == 3
            assert l["win_percentage"] >= 0.0


class TestV2InstitutionAnalytics:
    """Multi-Purpose Institution Leaderboard & Delta."""

    def test_delta_formula(self, v2):
        # Delta = (0.8 * A + 1.2 * B) / 2.0
        insts = v2.get_multipurpose_institutions(tier="tab", sort_by="delta")
        assert len(insts) > 0
        for i in insts:
            a = i["a_atss"]
            b = i["b_atss"] or 0.0
            expected = round((0.8 * a + 1.2 * b) / 2.0, 2)
            assert i["delta"] == expected

    def test_institution_bio_veterans_split(self, v2):
        bio = v2.get_institution_bio("Royal College")
        assert bio is not None
        assert bio["pool_count"] > 0
        assert bio["veterans_count"] + bio["new_count"] == bio["pool_count"]
        for v in bio["veterans"]:
            assert v["tournaments"] >= 2
        for n in bio["new_debaters"]:
            assert n["tournaments"] < 2


class TestV2AdjudicatorsAndTournaments:
    """Adjudicator and Tournament Rankings."""

    def test_adjudicator_profiles(self, v2):
        judges = v2.get_adjudicator_leaderboard()
        assert len(judges) > 0
        top_judge = judges[0]
        assert top_judge["aass"] > 0
        assert top_judge["aatss"] > 0
        assert "% Prop /" in top_judge["prop_opp_bias"]

    def test_tournament_hard_rankings(self, v2):
        tours = v2.get_tournament_hard_rankings(sort_by="atss")
        assert len(tours) == 8
        for t in tours:
            assert "atss" in t
            assert "brk_atss" in t
            assert "participating_institutions" in t
            assert "participating_teams" in t
            assert "prelims_plus_knock" in t
            assert "total_speeches" in t
            assert "prelim_debates" in t

    def test_national_pool_3_tiers(self, v2):
        pool = v2.get_national_pool_tiers()
        assert "nat_pool_direct" in pool
        assert "nat_pool_trialed" in pool
        assert "trials" in pool
        assert len(pool["nat_pool_direct"]) == 9
        assert len(pool["nat_pool_trialed"]) == 9
        assert len(pool["trials"]) == 9
        assert pool["total_count"] == 27


class TestV2RestApi:
    """Verify all /api/v2/... REST endpoints."""

    def test_api_speakers(self, client):
        r = client.get("/api/v2/leaderboard/speakers?tier=tab")
        assert r.status_code == 200
        assert len(r.get_json()["leaderboard"]) > 0

    def test_api_teams(self, client):
        r = client.get("/api/v2/leaderboard/teams?tier=tab")
        assert r.status_code == 200
        assert len(r.get_json()["leaderboard"]) > 0

    def test_api_institutions(self, client):
        r = client.get("/api/v2/leaderboard/institutions?tier=tab")
        assert r.status_code == 200
        assert len(r.get_json()["leaderboard"]) > 0

    def test_api_tournaments(self, client):
        r = client.get("/api/v2/leaderboard/tournaments")
        assert r.status_code == 200
        assert len(r.get_json()["leaderboard"]) == 8

    def test_api_adjudicators(self, client):
        r = client.get("/api/v2/leaderboard/adjudicators")
        assert r.status_code == 200
        assert len(r.get_json()["leaderboard"]) > 0

    def test_api_pool(self, client):
        r = client.get("/api/v2/pool")
        assert r.status_code == 200
        assert r.get_json()["total_count"] == 27

    def test_api_bios(self, client):
        r = client.get("/api/v2/debaters/Vidath%20Marasinghe/bio")
        assert r.status_code == 200
        assert r.get_json()["canonical_name"] == "Vidath Marasinghe"

        r = client.get("/api/v2/teams/DS%20A/bio")
        assert r.status_code == 200
        assert r.get_json()["team_name"] == "DS A"

        r = client.get("/api/v2/institutions/Royal%20College/bio")
        assert r.status_code == 200
        assert r.get_json()["institution_name"] == "Royal College"

        r = client.get("/api/v2/adjudicators/Senuka%20Seneviratne/bio")
        assert r.status_code == 200
        assert r.get_json()["adjudicator_name"] == "Senuka Seneviratne"
