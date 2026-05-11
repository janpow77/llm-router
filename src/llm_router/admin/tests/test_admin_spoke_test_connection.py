"""Tests fuer den ``POST /admin/api/spokes/test-connection``-Endpoint.

Der Endpoint ruft einen externen Provider via httpx auf. Wir patchen
``httpx.AsyncClient.get`` so, dass kein echter Netzwerk-Call passiert.
"""
from __future__ import annotations

import pytest

from llm_router.admin.services import spoke_test


class _FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None, raise_json: bool = False):
        self.status_code = status_code
        self._payload = payload
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """Async-Context-Manager der einen vorbereiteten _FakeResponse zurueckliefert.

    Speichert Aufruf-URL + Headers fuer Assertions.
    """

    instances: list[_FakeClient] = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.last_url: str | None = None
        self.last_headers: dict | None = None
        _FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        self.last_url = url
        self.last_headers = dict(headers or {})
        return _FakeClient.next_response


@pytest.fixture(autouse=True)
def _reset_fakeclient():
    _FakeClient.instances.clear()
    _FakeClient.next_response = None
    yield


def _patch_httpx(monkeypatch, response):
    _FakeClient.next_response = response
    monkeypatch.setattr(spoke_test.httpx, "AsyncClient", _FakeClient)


def test_test_connection_requires_auth(client):
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "https://api.openai.com"},
    )
    assert r.status_code == 401


def test_test_connection_openai_style_ok(client, auth_headers, monkeypatch):
    """OpenAI-Stil: ``{"data": [{"id": "..."}]}`` → models_count=2."""
    _patch_httpx(
        monkeypatch,
        _FakeResponse(200, {"data": [{"id": "gpt-4o"}, {"id": "gpt-3.5-turbo"}]}),
    )
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={
            "base_url": "https://api.openai.com",
            "auth_header": "Authorization",
            "auth_value": "Bearer sk-test",
            "test_endpoint": "/v1/models",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == 200
    assert body["models_count"] == 2
    assert "gpt-4o" in body["sample_models"]
    assert isinstance(body["latency_ms"], int)
    # Sicherheit: Auth-Header wird an Backend weitergereicht, aber NICHT
    # in der Response gespiegelt.
    instance = _FakeClient.instances[-1]
    assert instance.last_headers.get("Authorization") == "Bearer sk-test"
    assert "sk-test" not in r.text


def test_test_connection_ollama_style_ok(client, auth_headers, monkeypatch):
    _patch_httpx(
        monkeypatch,
        _FakeResponse(200, {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:7b"}]}),
    )
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={
            "base_url": "http://localhost:11434",
            "test_endpoint": "/api/tags",
        },
        headers=auth_headers,
    )
    body = r.json()
    assert body["ok"] is True
    assert body["models_count"] == 2
    assert "llama3.1:8b" in body["sample_models"]


def test_test_connection_401_returns_ok_false(client, auth_headers, monkeypatch):
    """Provider antwortet mit 401 — Endpoint liefert ok=False, leakt aber keinen Body."""
    _patch_httpx(monkeypatch, _FakeResponse(401, {"error": "Invalid token sk-leak"}))
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={
            "base_url": "https://api.openai.com",
            "auth_header": "Authorization",
            "auth_value": "Bearer sk-bad",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["status"] == 401
    assert body["error"] == "HTTP 401"
    # Body des Providers NICHT durchreichen
    assert "sk-leak" not in r.text


def test_test_connection_connect_error(client, auth_headers, monkeypatch):
    import httpx as real_httpx

    class _ConnFail:
        instances: list = []

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(spoke_test.httpx, "AsyncClient", _ConnFail)
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "http://127.0.0.1:1"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "connection failed" in body["error"]


def test_test_connection_default_endpoint(client, auth_headers, monkeypatch):
    """Ohne test_endpoint → /v1/models als Default."""
    _patch_httpx(monkeypatch, _FakeResponse(200, {"data": []}))
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "https://api.mistral.ai"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    instance = _FakeClient.instances[-1]
    assert instance.last_url.endswith("/v1/models")
    body = r.json()
    assert body["ok"] is True
    assert body["models_count"] == 0


def test_test_connection_non_json_2xx_is_ok(client, auth_headers, monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(200, payload=None, raise_json=True))
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "https://example.com", "test_endpoint": "/health"},
        headers=auth_headers,
    )
    body = r.json()
    assert body["ok"] is True
    assert body["models_count"] == 0


def test_test_connection_strips_trailing_slash(client, auth_headers, monkeypatch):
    _patch_httpx(monkeypatch, _FakeResponse(200, {"data": []}))
    r = client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "https://api.openai.com/", "test_endpoint": "v1/models"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    instance = _FakeClient.instances[-1]
    # Doppelte Slashes vermeiden, fuehrender Slash am Endpoint ergaenzt.
    assert instance.last_url == "https://api.openai.com/v1/models"


def test_test_connection_does_not_persist(client, auth_headers, monkeypatch):
    """Test-Connection darf KEINEN Spoke anlegen."""
    _patch_httpx(monkeypatch, _FakeResponse(200, {"data": [{"id": "x"}]}))
    pre = client.get("/admin/api/spokes", headers=auth_headers).json()
    client.post(
        "/admin/api/spokes/test-connection",
        json={"base_url": "https://api.openai.com"},
        headers=auth_headers,
    )
    post = client.get("/admin/api/spokes", headers=auth_headers).json()
    assert len(pre) == len(post)
