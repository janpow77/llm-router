"""Audit-Log-Tests."""
from __future__ import annotations


def test_audit_records_app_create(client, auth_headers):
    client.post("/admin/api/apps", json={"name": "auditme"}, headers=auth_headers)
    r = client.get("/admin/api/audit", headers=auth_headers)
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 1
    assert any(e["action"] == "app.create" for e in entries)


def test_audit_records_update_with_diff(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "diffme"}, headers=auth_headers).json()
    client.patch(
        f"/admin/api/apps/{create['id']}",
        json={"description": "after"},
        headers=auth_headers,
    )
    r = client.get("/admin/api/audit?action=app.update", headers=auth_headers)
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 1
    update = entries[0]
    assert update["before"]["description"] == ""
    assert update["after"]["description"] == "after"


def test_audit_records_delete(client, auth_headers):
    create = client.post("/admin/api/apps", json={"name": "delaud"}, headers=auth_headers).json()
    client.delete(f"/admin/api/apps/{create['id']}", headers=auth_headers)
    r = client.get("/admin/api/audit?action=app.delete", headers=auth_headers)
    entries = r.json()
    assert any(e["target"] == create["id"] for e in entries)


def test_audit_filter_by_actor(client, auth_headers):
    client.post("/admin/api/apps", json={"name": "actorf"}, headers=auth_headers)
    r = client.get("/admin/api/audit?actor=admin", headers=auth_headers)
    assert all(e["actor"] == "admin" for e in r.json())


def test_audit_does_not_log_secrets(client, auth_headers):
    """API-Key-Klartext darf nicht im Audit-Log auftauchen."""
    create = client.post("/admin/api/apps", json={"name": "secret"}, headers=auth_headers).json()
    plain_key = create["api_key"]
    r = client.get("/admin/api/audit", headers=auth_headers)
    body = r.text
    assert plain_key not in body, "API-Key-Klartext ist im Audit-Log gelandet!"


def test_audit_requires_auth(client):
    r = client.get("/admin/api/audit")
    assert r.status_code == 401


def test_settings_get(client, auth_headers):
    r = client.get("/admin/api/settings", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "router_version" in body
    assert "default_quotas" in body
    assert body["log_retention_days"] == 30


def test_settings_patch(client, auth_headers):
    r = client.patch(
        "/admin/api/settings",
        json={"log_retention_days": 90, "spoke_health_interval_s": 60},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["log_retention_days"] == 90
    assert r.json()["spoke_health_interval_s"] == 60


def test_dashboard_returns_zeros_with_empty_metrics(client, auth_headers, monkeypatch):
    """Wenn keine metrics.db da ist, soll das Dashboard mit Nullen antworten, nicht crashen."""
    # Sicherstellen, dass nichts gefunden wird
    monkeypatch.setenv("METRICS_DB_PATH", "/nonexistent/x.db")
    r = client.get("/admin/api/dashboard", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["requests_today"] == 0
    assert body["errors_today"] == 0
    assert "active_spokes" in body
    assert "active_apps" in body
