"""Auth-Tests."""
from __future__ import annotations


def test_login_success(client):
    r = client.post("/admin/api/auth/login", json={"password": "test-pw"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert "expires_at" in body
    assert len(body["token"]) > 20


def test_login_failure(client):
    r = client.post("/admin/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid password"


def test_me_requires_auth(client):
    r = client.get("/admin/api/auth/me")
    assert r.status_code == 401


def test_me_with_token(client, auth_headers):
    r = client.get("/admin/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["logged_in"] is True


def test_logout_invalidates(client, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = client.post("/admin/api/auth/logout", headers=headers)
    assert r.status_code == 204
    # Nach Logout 401
    r2 = client.get("/admin/api/auth/me", headers=headers)
    assert r2.status_code == 401


def test_invalid_token(client):
    r = client.get("/admin/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_health_open(client):
    r = client.get("/admin/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "spokes_health" in body
