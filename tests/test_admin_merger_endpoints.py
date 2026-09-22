"""
Unit tests for Institution Team Explorer & Search Autocomplete API endpoints.
"""

import sqlite3
import pytest
from pathlib import Path
from atomos.server import create_app, ADMIN_PASSWORD


@pytest.fixture
def test_client():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    schema_path = Path("src/atomos/database/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    # Seed test data
    cur = conn.cursor()
    cur.execute("INSERT INTO tournaments (id, slug, name, source_url) VALUES (1, 't1', 'Tournament Alpha', 'http://t1')")
    cur.execute("INSERT INTO tournaments (id, slug, name, source_url) VALUES (2, 't2', 'Tournament Beta', 'http://t2')")

    cur.execute("INSERT INTO institutions (id, name, code) VALUES (1, 'Royal College', 'RC')")
    cur.execute("INSERT INTO institutions (id, name, code) VALUES (2, 'Trinity College', 'TC')")

    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (10, 1, 'Royal A', 1)")
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (11, 2, 'Royal College A', 1)")
    cur.execute("INSERT INTO teams (id, tournament_id, name, institution_id) VALUES (20, 1, 'Trinity A', 2)")

    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (101, 'Vidath Marasinghe')")
    cur.execute("INSERT INTO persons (id, canonical_name) VALUES (102, 'Balishta Wijesinghe')")

    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (10, 101)")
    cur.execute("INSERT INTO team_members (team_id, person_id) VALUES (11, 101)")

    conn.commit()

    app = create_app(db_conn=conn)
    app.config["TESTING"] = True
    client = app.test_client()

    # Login to get admin token
    res = client.post("/api/admin/login", json={"password": ADMIN_PASSWORD})
    token = res.json["token"]

    return client, token


def test_institutions_list(test_client):
    client, token = test_client

    # 401 without token
    res_unauth = client.get("/api/admin/institutions/list")
    assert res_unauth.status_code == 401

    # Authorized request
    res = client.get("/api/admin/institutions/list", headers={"X-Admin-Token": token})
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert data["count"] == 2
    names = [inst["name"] for inst in data["institutions"]]
    assert "Royal College" in names
    assert "Trinity College" in names


def test_institution_teams_lookup(test_client):
    client, token = test_client

    # Lookup by name
    res = client.get("/api/admin/institutions/Royal%20College/teams", headers={"X-Admin-Token": token})
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert data["institution"]["name"] == "Royal College"
    assert len(data["teams"]) == 2
    team_names = [t["name"] for t in data["teams"]]
    assert "Royal A" in team_names
    assert "Royal College A" in team_names
    assert data["teams"][0]["members"] == "Vidath Marasinghe"

    # Lookup by ID
    res_id = client.get("/api/admin/institutions/2/teams", headers={"X-Admin-Token": token})
    assert res_id.status_code == 200
    assert res_id.json["institution"]["name"] == "Trinity College"
    assert len(res_id.json["teams"]) == 1

    # Lookup 404
    res_404 = client.get("/api/admin/institutions/NonExistentSchool/teams", headers={"X-Admin-Token": token})
    assert res_404.status_code == 404


def test_entities_search_person(test_client):
    client, token = test_client

    # Search person by name
    res = client.get("/api/admin/entities/search?type=person&q=Vidath", headers={"X-Admin-Token": token})
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert len(data["results"]) == 1
    assert data["results"][0]["canonical_name"] == "Vidath Marasinghe"
    assert data["results"][0]["id"] == 101

    # Search person by numeric ID
    res_id = client.get("/api/admin/entities/search?type=person&q=102", headers={"X-Admin-Token": token})
    assert res_id.status_code == 200
    assert len(res_id.json["results"]) == 1
    assert res_id.json["results"][0]["canonical_name"] == "Balishta Wijesinghe"


def test_entities_search_team(test_client):
    client, token = test_client

    # Search team by name
    res = client.get("/api/admin/entities/search?type=team&q=Royal", headers={"X-Admin-Token": token})
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert len(data["results"]) == 2

    # Search team by ID
    res_id = client.get("/api/admin/entities/search?type=team&q=20", headers={"X-Admin-Token": token})
    assert res_id.status_code == 200
    assert len(res_id.json["results"]) == 1
    assert res_id.json["results"][0]["name"] == "Trinity A"
