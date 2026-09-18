"""
Tests for Atomos Headless REST API (Fold 4)
"""

import pytest

from atomos.database.connection import get_connection
from atomos.server import create_app


@pytest.fixture
def client():
    conn = get_connection()
    app = create_app(db_conn=conn)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    conn.close()


class TestAtomosApiEndpoints:
    def test_health_endpoint(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "online"
        assert data["database"]["active"] is True
        assert data["database"]["persons_indexed"] > 500

    def test_cors_headers(self, client):
        res = client.get("/api/health")
        assert res.headers.get("Access-Control-Allow-Origin") == "*"
        assert "GET" in res.headers.get("Access-Control-Allow-Methods", "")

    def test_ask_endpoint(self, client):
        payload = {"query": "Who is Balishta Wijesinghe?"}
        res = client.post("/api/ask", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["intent"] in ("DEBATER_DOSSIER", "GEMINI_LLM")
        assert "Balishta Wijesinghe" in data["answer"]

    def test_ask_endpoint_missing_query(self, client):
        res = client.post("/api/ask", json={})
        assert res.status_code == 400
        data = res.get_json()
        assert "error" in data

    def test_search_endpoint(self, client):
        res = client.get("/api/search?q=Royal&limit=5")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["results"]) > 0
        assert any("Royal" in r["name"] for r in data["results"])

    def test_get_debater_endpoint(self, client):
        res = client.get("/api/debaters/42")
        assert res.status_code == 200
        data = res.get_json()
        assert data["person_id"] == 42
        assert data["canonical_name"] == "Balishta Wijesinghe"
        assert data["institution"] == "D. S. Senanayake College"
        assert data["speech_average"] == 71.15

    def test_get_debater_derivation_endpoint(self, client):
        res = client.get("/api/debaters/42/derivation")
        assert res.status_code == 200
        data = res.get_json()
        assert data["person_id"] == 42
        assert "derivation_text" in data
        assert "WSDC & Atomos Master Tab Standardization Rules" in data["derivation_text"]

    def test_get_debater_404(self, client):
        res = client.get("/api/debaters/999999")
        assert res.status_code == 404

    def test_h2h_endpoint(self, client):
        res = client.get("/api/h2h?a=Royal%20College&b=Ananda%20College")
        assert res.status_code == 200
        data = res.get_json()
        assert data["comparison_type"] == "school"

    def test_institutions_leaderboard_endpoint(self, client):
        res = client.get("/api/institutions?top=5")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["leaderboard"]) <= 5
        assert data["leaderboard"][0]["rank"] == 1

    def test_institution_dossier_endpoint(self, client):
        res = client.get("/api/institutions/RC")
        assert res.status_code == 200
        data = res.get_json()
        assert data["name"] == "Royal College"
        assert data["code"] == "RC"

    def test_institution_compare_endpoint(self, client):
        res = client.get("/api/institutions/compare?a=RC&b=DS")
        assert res.status_code == 200
        data = res.get_json()
        assert data["inst_a"]["code"] == "RC"
        assert data["inst_b"]["code"] == "DS"

    def test_motions_summary_endpoint(self, client):
        res = client.get("/api/motions/summary")
        assert res.status_code == 200
        data = res.get_json()
        assert "overall_side_balance" in data
        assert "thematic_analysis" in data

    def test_circuit_summary_endpoint(self, client):
        res = client.get("/api/circuit")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total_tournaments"] > 0
        assert data["total_debates_debated"] > 0

    def test_debater_profile_endpoint(self, client):
        res = client.get("/api/debaters/42/profile")
        assert res.status_code == 200
        data = res.get_json()
        assert data["person_id"] == 42
        assert "speech_average" in data
        assert "trajectory" in data
        assert isinstance(data["trajectory"], list)

    def test_leaderboard_speakers_endpoint(self, client):
        res = client.get("/api/leaderboard/speakers?metric=prelims&limit=5")
        assert res.status_code == 200
        data = res.get_json()
        assert "metric" in data
        assert len(data["leaderboard"]) <= 5

    def test_tournament_bracket_endpoint(self, client):
        res = client.get("/api/tournaments/Chaps2026/bracket")
        assert res.status_code == 200
        data = res.get_json()
        assert "Chap" in data["tournament_name"]
        assert len(data["stages"]) > 0

    def test_tournament_bracket_404(self, client):
        res = client.get("/api/tournaments/FakeTourn999/bracket")
        assert res.status_code == 404

    def test_judge_dossier_endpoint(self, client):
        res = client.get("/api/judges/Minithi%20Hewage")
        assert res.status_code == 200
        data = res.get_json()
        assert "Minithi" in data["adjudicator_name"]

    def test_judge_leaderboard_endpoint(self, client):
        res = client.get("/api/judges?limit=5")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["leaderboard"]) <= 5

    def test_predict_matchup_endpoint(self, client):
        res = client.get("/api/predict?team_a=DS%20A&team_b=RC%20A")
        assert res.status_code == 200
        data = res.get_json()
        assert "simulation" in data
        assert data["simulation"]["projected_margin"] > 0

    def test_national_pool_endpoint(self, client):
        res = client.get("/api/national-pool")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total_contingent"] == 27
        assert "debaters" in data

    def test_debate_ballot_endpoint(self, client):
        res = client.get("/api/debates/3411")
        assert res.status_code == 200
        data = res.get_json()
        assert data["debate_id"] == 3411
        assert data["proposition"]["team_name"] == "DS B"

