"""Spokes-CRUD-Tests."""
from __future__ import annotations


def test_create_spoke(client, auth_headers):
    payload = {
        "name": "nuc-test",
        "base_url": "http://localhost:11434/",
        "type": "ollama",
        "enabled": True,
    }
    r = client.post("/admin/api/spokes", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "nuc-test"
    assert body["base_url"] == "http://localhost:11434"  # trailing slash gestrippt
    assert body["status"] in ("online", "offline", "unknown")  # initial discover passiert


def test_list_spokes(client, auth_headers):
    client.post("/admin/api/spokes", json={"name": "a", "base_url": "http://a"}, headers=auth_headers)
    client.post("/admin/api/spokes", json={"name": "b", "base_url": "http://b"}, headers=auth_headers)
    r = client.get("/admin/api/spokes", headers=auth_headers)
    assert r.status_code == 200
    names = sorted(s["name"] for s in r.json())
    assert names == ["a", "b"]


def test_create_spoke_duplicate(client, auth_headers):
    r1 = client.post("/admin/api/spokes", json={"name": "dup", "base_url": "http://x"}, headers=auth_headers)
    assert r1.status_code == 201
    r2 = client.post("/admin/api/spokes", json={"name": "dup", "base_url": "http://y"}, headers=auth_headers)
    assert r2.status_code == 409


def test_patch_spoke(client, auth_headers):
    create = client.post("/admin/api/spokes", json={"name": "p", "base_url": "http://x"}, headers=auth_headers).json()
    r = client.patch(
        f"/admin/api/spokes/{create['id']}",
        json={"base_url": "http://y/", "enabled": False},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["base_url"] == "http://y"
    assert body["enabled"] is False


def test_delete_spoke(client, auth_headers):
    create = client.post("/admin/api/spokes", json={"name": "d", "base_url": "http://z"}, headers=auth_headers).json()
    r = client.delete(f"/admin/api/spokes/{create['id']}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get(f"/admin/api/spokes/{create['id']}", headers=auth_headers)
    assert r2.status_code == 404


def test_spoke_health_check_on_unreachable(client, auth_headers):
    """Spoke ohne erreichbares Backend soll als offline markiert werden."""
    create = client.post(
        "/admin/api/spokes",
        json={"name": "unreach", "base_url": "http://127.0.0.1:1"},
        headers=auth_headers,
    ).json()
    r = client.post(f"/admin/api/spokes/{create['id']}/health-check", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "offline"
    assert body["last_error"]


def test_spokes_require_auth(client):
    assert client.get("/admin/api/spokes").status_code == 401
    assert client.post("/admin/api/spokes", json={"name": "x", "base_url": "y"}).status_code == 401


def test_routes_crud(client, auth_headers):
    spoke = client.post(
        "/admin/api/spokes", json={"name": "rt-spoke", "base_url": "http://x"}, headers=auth_headers,
    ).json()
    create = client.post(
        "/admin/api/routes",
        json={"model_glob": "qwen3:*", "spoke_id": spoke["id"], "priority": 10, "enabled": True},
        headers=auth_headers,
    )
    assert create.status_code == 201
    rid = create.json()["id"]
    listed = client.get("/admin/api/routes", headers=auth_headers).json()
    assert any(r["id"] == rid for r in listed)
    patched = client.patch(f"/admin/api/routes/{rid}", json={"priority": 5}, headers=auth_headers)
    assert patched.status_code == 200
    assert patched.json()["priority"] == 5
    deleted = client.delete(f"/admin/api/routes/{rid}", headers=auth_headers)
    assert deleted.status_code == 204


def test_route_create_invalid_spoke(client, auth_headers):
    r = client.post(
        "/admin/api/routes",
        json={"model_glob": "*", "spoke_id": "spk_nope", "priority": 100, "enabled": True},
        headers=auth_headers,
    )
    assert r.status_code == 400
