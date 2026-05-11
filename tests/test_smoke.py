"""Smoke-Tests für llm-router.

Nutzt FastAPI TestClient mit gemockten httpx-Calls. Macht keine echten
Spoke-Calls (würde NUC-Ollama unnötig belasten).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
server:
  host: 127.0.0.1
  port: 7842
auth:
  require_app_id: true
  allow_default: true
apps:
  - id: default
    rate_limit_rpm: 60
    max_concurrent: 4
  - id: test
    rate_limit_rpm: 60
    max_concurrent: 4
spokes:
  - name: mock
    url: http://mock-spoke.local:11434
    scheme: ollama
    timeout_s: 10
routes:
  - model_glob: "*"
    spoke: mock
metrics:
  db_path: %s
        """
        % (tmp_path / "metrics.db"),
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_ROUTER_CONFIG", str(cfg))

    from llm_router.main import app as fastapi_app

    return fastapi_app


def test_health_no_spokes_reachable(app, monkeypatch):
    """Spokes nicht erreichbar — Status sollte degraded sein, aber 200 zurückkommen."""
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "version" in body
    assert isinstance(body["spokes"], list)


def test_admin_api_health_open(app):
    """Health-Endpoint ist ohne Auth erreichbar."""
    with TestClient(app) as client:
        r = client.get("/admin/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "spokes_health" in body


def test_admin_api_requires_auth(app):
    """Geschuetzter Endpoint liefert 401 ohne Bearer."""
    with TestClient(app) as client:
        r = client.get("/admin/api/apps")
    assert r.status_code == 401


def test_admin_api_login_and_apps(app):
    """Login mit Test-Passwort + authentifizierter Apps-Call."""
    with TestClient(app) as client:
        login = client.post("/admin/api/auth/login", json={"password": "test-password"})
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        r = client.get("/admin/api/apps", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_api_dashboard(app):
    with TestClient(app) as client:
        token = client.post(
            "/admin/api/auth/login", json={"password": "test-password"}
        ).json()["token"]
        r = client.get(
            "/admin/api/dashboard", headers={"Authorization": f"Bearer {token}"}
        )
    assert r.status_code == 200
    body = r.json()
    assert "requests_today" in body
    assert "active_spokes" in body


def test_root_redirects_to_admin(app):
    with TestClient(app) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin" in r.headers.get("location", "")


def test_unknown_app_falls_back_to_default(app, monkeypatch):
    """Wenn allow_default=true: unbekannte X-App-Id => default."""

    # Wir mocken httpx.AsyncClient um die Spoke-Anfrage abzufangen.
    import httpx as _httpx

    class MockResp:
        status_code = 200
        headers = _httpx.Headers({"content-type": "application/json"})

        async def aiter_raw(self):
            yield b'{"models":[]}'

        async def aread(self):
            return b'{"models":[]}'

        async def aclose(self):
            return None

    class MockClient:
        def __init__(self, *a, **kw):
            pass

        def build_request(self, *a, **kw):
            return _httpx.Request(a[0], a[1])

        async def send(self, *a, **kw):
            return MockResp()

        async def aclose(self):
            return None

    monkeypatch.setattr("llm_router.proxy.httpx.AsyncClient", MockClient)

    with TestClient(app) as client:
        r = client.get("/api/tags", headers={"X-App-Id": "unknown-app"})
    # Sollte nicht 401/403 sein da allow_default=true
    assert r.status_code in (200, 502, 503), f"unexpected status {r.status_code}: {r.text}"


def test_admin_api_paths_no_app_id_header(app):
    """Admin-API darf ohne X-App-Id aufgerufen werden — die App-ID ist nur fuer
    durchgereichte LLM-Calls relevant, nicht fuer Verwaltungsendpoints."""
    with TestClient(app) as client:
        r = client.get("/admin/api/health")
    assert r.status_code == 200
