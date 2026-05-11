"""Apps-CRUD-Tests."""
from __future__ import annotations


def test_create_app_returns_plain_key(client, auth_headers):
    payload = {
        "name": "audit_designer",
        "description": "test",
        "allowed_models": ["qwen3:14b"],
        "quota": {"rpm": 240, "concurrent": 16, "daily_tokens": 5_000_000},
    }
    r = client.post("/admin/api/apps", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "api_key" in body
    # Prefix wird aus dem Namen abgeleitet (max 12 Zeichen, nur a-z0-9)
    assert body["api_key"].startswith("auditdesigne_")
    assert body["api_key_preview"].startswith("auditdesigne_••••")
    assert body["allowed_models"] == ["qwen3:14b"]
    assert body["quota"]["rpm"] == 240
    assert body["enabled"] is True


def test_list_apps_empty(client, auth_headers):
    r = client.get("/admin/api/apps", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_apps_after_create(client, auth_headers):
    client.post("/admin/api/apps", json={"name": "x"}, headers=auth_headers)
    client.post("/admin/api/apps", json={"name": "y"}, headers=auth_headers)
    r = client.get("/admin/api/apps", headers=auth_headers)
    assert r.status_code == 200
    names = sorted(a["name"] for a in r.json())
    assert names == ["x", "y"]


def test_create_app_duplicate_name(client, auth_headers):
    r1 = client.post("/admin/api/apps", json={"name": "dup"}, headers=auth_headers)
    assert r1.status_code == 201
    r2 = client.post("/admin/api/apps", json={"name": "dup"}, headers=auth_headers)
    assert r2.status_code == 409


def test_get_app_detail(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "detail"}, headers=auth_headers).json()
    r = client.get(f"/admin/api/apps/{create['id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "detail"
    assert "recent_requests" in body
    assert isinstance(body["recent_requests"], list)


def test_get_app_404(client, auth_headers):
    r = client.get("/admin/api/apps/app_doesnotexist", headers=auth_headers)
    assert r.status_code == 404


def test_patch_app_partial(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "patchme"}, headers=auth_headers).json()
    r = client.patch(
        f"/admin/api/apps/{create['id']}",
        json={"description": "new desc", "quota": {"rpm": 1000, "concurrent": 32, "daily_tokens": 0}},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"] == "new desc"
    assert body["quota"]["rpm"] == 1000


def test_delete_app(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "delme"}, headers=auth_headers).json()
    r = client.delete(f"/admin/api/apps/{create['id']}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get(f"/admin/api/apps/{create['id']}", headers=auth_headers)
    assert r2.status_code == 404


def test_rotate_key_changes_preview(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "rot"}, headers=auth_headers).json()
    old_preview = create["api_key_preview"]
    r = client.post(f"/admin/api/apps/{create['id']}/rotate-key", headers=auth_headers)
    assert r.status_code == 200
    assert "api_key" in r.json()
    after = client.get(f"/admin/api/apps/{create['id']}", headers=auth_headers).json()
    assert after["api_key_preview"] != old_preview


def test_toggle_enabled(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "tog"}, headers=auth_headers).json()
    assert create["enabled"] is True
    r = client.post(f"/admin/api/apps/{create['id']}/toggle-enabled", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    r2 = client.post(f"/admin/api/apps/{create['id']}/toggle-enabled", headers=auth_headers)
    assert r2.json()["enabled"] is True


def test_apps_require_auth(client):
    r = client.get("/admin/api/apps")
    assert r.status_code == 401
    r2 = client.post("/admin/api/apps", json={"name": "x"})
    assert r2.status_code == 401


def test_quota_get_and_patch(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "q"}, headers=auth_headers).json()
    r = client.get(f"/admin/api/quotas/{create['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["limits"]["rpm"] == 60
    r2 = client.patch(f"/admin/api/quotas/{create['id']}", json={"rpm": 999}, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["limits"]["rpm"] == 999
