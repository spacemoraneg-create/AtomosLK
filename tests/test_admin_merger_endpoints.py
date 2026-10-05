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


def test_institution_team_names_grouping(test_client):
    client, token = test_client

    res = client.get("/api/admin/institutions/1/teams", headers={"X-Admin-Token": token})
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "team_names" in data
    assert data["count"] == 2
    assert data["total_instances"] == 2

    # Check distinct team name objects
    names = {tn["name"]: tn for tn in data["team_names"]}
    assert "Royal A" in names
    assert "Royal College A" in names

    ra = names["Royal A"]
    assert ra["canonical_name"] == "Royal A"
    assert ra["instance_count"] == 1
    assert ra["is_merged"] is False
    assert len(ra["tournaments"]) == 1
    assert ra["members"] == "Vidath Marasinghe"


def test_institution_merge_and_unmerge_team_names(test_client):
    client, token = test_client

    # 1. Merge "Royal College A" into canonical "Royal A"
    merge_res = client.post(
        "/api/admin/institutions/merge_team_names",
        headers={"X-Admin-Token": token},
        json={
            "institution_id": 1,
            "target_canonical_name": "Royal A",
            "variant_name": "Royal College A",
            "tier": "A"
        }
    )
    assert merge_res.status_code == 200
    merge_data = merge_res.json
    assert merge_data["success"] is True
    assert merge_data["target_canonical_name"] == "Royal A"
    assert merge_data["variant_name"] == "Royal College A"
    assert merge_data["instances_updated"] == 1

    # 2. Verify state via GET
    get_res = client.get("/api/admin/institutions/1/teams", headers={"X-Admin-Token": token})
    assert get_res.status_code == 200
    get_data = get_res.json

    # Confirmed merges list has 1 item
    assert len(get_data["confirmed_merges"]) == 1
    cm = get_data["confirmed_merges"][0]
    assert cm["target_canonical_name"] == "Royal A"
    assert cm["variant_name"] == "Royal College A"

    # In team_names list
    names = {tn["name"]: tn for tn in get_data["team_names"]}
    assert names["Royal A"]["merged_variants"] == ["Royal College A"]
    assert names["Royal College A"]["is_merged"] is True
    assert names["Royal College A"]["merged_into"] == "Royal A"

    # 3. Unmerge "Royal College A"
    unmerge_res = client.post(
        "/api/admin/institutions/unmerge_team_name",
        headers={"X-Admin-Token": token},
        json={
            "institution_id": 1,
            "variant_name": "Royal College A"
        }
    )
    assert unmerge_res.status_code == 200
    assert unmerge_res.json["success"] is True

    # 4. Verify state after unmerge
    get_res2 = client.get("/api/admin/institutions/1/teams", headers={"X-Admin-Token": token})
    assert get_res2.status_code == 200
    get_data2 = get_res2.json
    assert len(get_data2["confirmed_merges"]) == 0

    names2 = {tn["name"]: tn for tn in get_data2["team_names"]}
    assert names2["Royal A"]["merged_variants"] == []
    assert names2["Royal College A"]["is_merged"] is False
    assert names2["Royal College A"]["canonical_name"] == "Royal College A"


def test_institution_merge_validation_errors(test_client):
    client, token = test_client

    # Missing fields
    res_bad = client.post(
        "/api/admin/institutions/merge_team_names",
        headers={"X-Admin-Token": token},
        json={"institution_id": 1}
    )
    assert res_bad.status_code == 400

    # Non-existent institution
    res_no_inst = client.post(
        "/api/admin/institutions/merge_team_names",
        headers={"X-Admin-Token": token},
        json={
            "institution_id": 9999,
            "target_canonical_name": "Royal A",
            "variant_name": "Royal College A"
        }
    )
    assert res_no_inst.status_code == 404

    # Non-existent variant team
    res_no_var = client.post(
        "/api/admin/institutions/merge_team_names",
        headers={"X-Admin-Token": token},
        json={
            "institution_id": 1,
            "target_canonical_name": "Royal A",
            "variant_name": "Ghost Variant Team"
        }
    )
    assert res_no_var.status_code == 404

    # Unmerge missing fields
    res_unmerge_bad = client.post(
        "/api/admin/institutions/unmerge_team_name",
        headers={"X-Admin-Token": token},
        json={"institution_id": 1}
    )
    assert res_unmerge_bad.status_code == 400


def test_admin_update_tournament_dates(test_client):
    client, token = test_client

    # 1. 401 Unauthorized check
    res_unauth = client.post("/api/admin/tournaments/1/dates", json={"hosting_dates": "Oct 12–15, 2026"})
    assert res_unauth.status_code == 401

    # 2. 404 for non-existent tournament
    res_404 = client.post(
        "/api/admin/tournaments/999/dates",
        headers={"X-Admin-Token": token},
        json={"hosting_dates": "Oct 12–15, 2026"}
    )
    assert res_404.status_code == 404

    # 3. Successful date update by ID
    res_update = client.post(
        "/api/admin/tournaments/1/dates",
        headers={"X-Admin-Token": token},
        json={"hosting_dates": "Oct 12–15, 2026"}
    )
    assert res_update.status_code == 200
    data = res_update.json
    assert data["success"] is True
    assert data["hosting_dates"] == "Oct 12–15, 2026"
    assert data["tournament_id"] == 1

    # 4. Successful date update by slug
    res_slug = client.post(
        "/api/admin/tournaments/t2/dates",
        headers={"X-Admin-Token": token},
        json={"hosting_dates": "Nov 20–23, 2026"}
    )
    assert res_slug.status_code == 200
    assert res_slug.json["hosting_dates"] == "Nov 20–23, 2026"

    # 5. Status endpoint reflects updated hosting dates
    res_status = client.get("/api/admin/status", headers={"X-Admin-Token": token})
    assert res_status.status_code == 200
    t_list = res_status.json["tournaments"]
    t1 = next(t for t in t_list if t["id"] == 1)
    t2 = next(t for t in t_list if t["id"] == 2)
    assert t1["hosting_dates"] == "Oct 12–15, 2026"
    assert t2["hosting_dates"] == "Nov 20–23, 2026"


def test_github_sync_configuration(test_client):
    client, token = test_client

    # Check github status endpoint with header
    res = client.get(
        "/api/admin/github/status",
        headers={
            "X-Admin-Token": token,
            "X-GitHub-Token": "github_pat_test123",
        }
    )
    assert res.status_code == 200
    data = res.json
    assert data["configured"] is True
    assert data["repo"] == "spacemoraneg-create/AtomosLK"
    assert data["branch"] == "main"


