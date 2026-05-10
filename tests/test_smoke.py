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


def test_admin_stats(app):
    with TestClient(app) as client:
        r = client.get("/admin/stats")
    assert r.status_code == 200
    body = r.json()
    assert "totals_24h" in body
    assert "by_app" in body
    assert "spokes" in body


def test_admin_apps(app):
    with TestClient(app) as client:
        r = client.get("/admin/apps")
    assert r.status_code == 200
    apps = r.json()
    ids = [a["id"] for a in apps]
    assert "default" in ids
    assert "test" in ids


def test_admin_logs_initial_empty(app):
    with TestClient(app) as client:
        r = client.get("/admin/logs?limit=10")
    assert r.status_code == 200
    assert r.json() == []


def test_admin_ui_html(app):
    with TestClient(app) as client:
        r = client.get("/admin/")
    assert r.status_code == 200
    assert "<html" in r.text.lower()
    assert "llm-router" in r.text.lower()


def test_root_redirects_to_admin(app):
    with TestClient(app) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/admin" in r.headers.get("location", "")


def test_metrics_prometheus_format(app):
    with TestClient(app) as client:
        r = client.get("/admin/metrics")
    assert r.status_code == 200
    text = r.text
    assert "llm_router_requests_total" in text
    assert "llm_router_errors_total" in text


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


def test_require_app_id_off_allows_no_header(app):
    with TestClient(app) as client:
        # /admin/* braucht keine App-ID
        r = client.get("/admin/spokes")
    assert r.status_code == 200
