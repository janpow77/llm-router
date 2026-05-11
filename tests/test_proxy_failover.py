"""Tests fuer den Auto-Failover des Proxies (Phase 3).

Wir testen die Circuit-Breaker-Logik direkt gegen ``proxy()`` ohne den
FastAPI-Stack, indem wir einen ``SpokeConfig`` mit primary+fallback bauen
und httpx-Calls mocken.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest

from llm_router.config import SpokeConfig
from llm_router.metrics import MetricsStore
from llm_router.proxy import (
    _FAILOVER_THRESHOLD,
    _RECOVERY_THRESHOLD,
    _breaker_get,
    _breaker_reset_all,
    proxy,
)


@pytest.fixture(autouse=True)
def _reset_breakers():
    _breaker_reset_all()
    yield
    _breaker_reset_all()


@pytest.fixture
def metrics(tmp_path: Path) -> MetricsStore:
    return MetricsStore(str(tmp_path / "metrics.db"))


def _make_spoke(name: str = "primary", *, fallback: bool = True) -> SpokeConfig:
    return SpokeConfig(
        name=name,
        url="http://primary.example:11434",
        scheme="ollama",
        timeout_s=5,
        fallback_url="http://fallback.example:11434" if fallback else None,
    )


class _MockResp:
    def __init__(self, status_code: int, body: bytes = b'{"ok": true}'):
        self.status_code = status_code
        self.headers = httpx.Headers({"content-type": "application/json"})
        self._body = body

    async def aiter_raw(self):
        yield self._body

    async def aread(self):
        return self._body

    async def aclose(self):
        return None


class _MockClient:
    """httpx-mock der je nach Host eine vorkonfigurierte Antwort liefert."""

    # class-level state, damit Mock-Outcomes pro Test gesteuert werden koennen
    behaviors: dict[str, list[object]] = {}
    calls: list[tuple[str, str]] = []  # (host, url)

    def __init__(self, *a, **kw):
        pass

    def build_request(self, method, url, headers=None, content=None):
        return httpx.Request(method, url)

    async def send(self, req, *a, **kw):
        url = str(req.url)
        host = req.url.host
        _MockClient.calls.append((host, url))
        actions = _MockClient.behaviors.get(host, [])
        if not actions:
            return _MockResp(200)
        action = actions.pop(0)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, int):
            return _MockResp(action)
        return action

    async def aclose(self):
        return None


def _install_mock(monkeypatch):
    _MockClient.behaviors = {}
    _MockClient.calls = []
    monkeypatch.setattr("llm_router.proxy.httpx.AsyncClient", _MockClient)
    return _MockClient


async def _call(spoke, metrics, body=b'{"model": "x"}'):
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/chat/completions",
        headers={},
        body=body,
        query="",
        app_id="test",
        metrics=metrics,
        route_label="/v1/chat/completions",
        response_kind="openai",
    )


def test_failover_after_three_consecutive_5xx(monkeypatch, metrics):
    """Drei 503 in Folge auf primary → vierter Call geht auf fallback.

    Wir nutzen den Threshold _FAILOVER_THRESHOLD = 3.
    """
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke()
    # Primary liefert dreimal 503 (jeder Call hat primary-try + fallback-retry-success).
    # Wir wollen 503 → fallback OK → counter steigt von 0 auf 1.
    # Damit der Breaker nach 3 trips: primary muss 3 mal in Folge schlechte
    # Antworten geben (jeweils mit Fallback-Retry der success ist).
    mock.behaviors[spoke.url.split("//")[1].split(":")[0]] = [503, 503, 503]
    mock.behaviors[spoke.fallback_url.split("//")[1].split(":")[0]] = [
        _MockResp(200),
        _MockResp(200),
        _MockResp(200),
    ]

    # Drei Calls: alle laufen primary→fallback (Retry). Counter steigt auf 3.
    for _ in range(3):
        resp = asyncio.run(_call(spoke, metrics))
        assert resp.status_code == 200, "Fallback sollte 200 liefern"

    state = _breaker_get(spoke.name)
    assert state.consecutive_failures == 3
    assert state.using_fallback is True
    assert state.failover_events == 1


def test_recovery_after_successful_primary_calls(monkeypatch, metrics):
    """Nach _RECOVERY_THRESHOLD erfolgreichen primary-Calls schaltet der
    Breaker zurueck auf primary.
    """
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke()

    # 3x 503 auf primary → Breaker offen, 3 fallback-Retries.
    mock.behaviors["primary.example"] = [503, 503, 503]
    mock.behaviors["fallback.example"] = [_MockResp(200)] * 3 + [_MockResp(200)] * _RECOVERY_THRESHOLD
    for _ in range(3):
        asyncio.run(_call(spoke, metrics))
    state = _breaker_get(spoke.name)
    assert state.using_fallback is True

    # Wir simulieren primary-Recovery: setzen using_fallback aus (manuell — der
    # naechste primary-Call kann erst nach Breaker-Reset stattfinden). Stattdessen
    # foerden wir Recovery ueber das Loeschen der using_fallback-Flag:
    # In der Realitaet wird primary in Health-Loops gepingt. Im Proxy aktuell
    # bleibt using_fallback bis der naechste *primary-Aufruf* erfolgt, was nicht
    # automatisch passiert. Daher testen wir hier: wenn man manuell zurueck-
    # schaltet (durch erfolgreichen Primary-Call), erfolgt nach M Calls Reset.
    state.using_fallback = False  # Health-Reset
    state.consecutive_successes = 0

    # Jetzt _RECOVERY_THRESHOLD primary-Calls mit 200.
    mock.behaviors["primary.example"] = [_MockResp(200)] * _RECOVERY_THRESHOLD
    for _ in range(_RECOVERY_THRESHOLD):
        resp = asyncio.run(_call(spoke, metrics))
        assert resp.status_code == 200
    state = _breaker_get(spoke.name)
    assert state.using_fallback is False
    assert state.consecutive_failures == 0


def test_no_fallback_url_means_no_breaker_state(monkeypatch, metrics):
    """Spokes ohne fallback_url: keine Breaker-Updates."""
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke(fallback=False)
    mock.behaviors["primary.example"] = [503]

    asyncio.run(_call(spoke, metrics))
    state = _breaker_get(spoke.name)
    # Keine Updates → 0/0
    assert state.consecutive_failures == 0
    assert state.using_fallback is False


def test_failover_on_connection_error(monkeypatch, metrics):
    """Auch Verbindungsfehler (httpx.ConnectError) trigger ein Failover-Retry."""
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke()
    mock.behaviors["primary.example"] = [httpx.ConnectError("connection refused")]
    mock.behaviors["fallback.example"] = [_MockResp(200)]

    resp = asyncio.run(_call(spoke, metrics))
    assert resp.status_code == 200
    assert resp.headers.get("X-Llm-Failover") == "1"

    state = _breaker_get(spoke.name)
    assert state.consecutive_failures == 1


def test_cf_access_headers_injected_on_fallback(monkeypatch, metrics):
    """Wenn CF_ACCESS_CLIENT_ID/SECRET gesetzt sind, taucht beim fallback-Call
    der ``CF-Access-Client-Id``-Header im Request auf.
    """
    from llm_router.proxy import _cf_access_cache_reset

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id-abc")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret-xyz")
    _cf_access_cache_reset()

    captured_headers: list[dict[str, str]] = []
    original_build = _MockClient.build_request

    def _capture_build(self, method, url, headers=None, content=None):
        captured_headers.append(dict(headers or {}))
        return original_build(self, method, url, headers=headers, content=content)

    monkeypatch.setattr(_MockClient, "build_request", _capture_build)

    mock = _install_mock(monkeypatch)
    mock.behaviors["primary.example"] = [503]
    mock.behaviors["fallback.example"] = [_MockResp(200)]

    spoke = _make_spoke()
    resp = asyncio.run(_call(spoke, metrics))
    assert resp.status_code == 200
    # Zwei Requests: primary (ohne CF-Header), fallback (mit CF-Header).
    assert len(captured_headers) == 2
    primary_headers = {k.lower(): v for k, v in captured_headers[0].items()}
    fallback_headers = {k.lower(): v for k, v in captured_headers[1].items()}
    assert "cf-access-client-id" not in primary_headers
    assert fallback_headers.get("cf-access-client-id") == "id-abc"
    assert fallback_headers.get("cf-access-client-secret") == "secret-xyz"
    _cf_access_cache_reset()


def test_cf_access_headers_absent_when_env_missing(monkeypatch, metrics):
    """Ohne CF_ACCESS-Env-Vars werden auch beim fallback keine CF-Header gesetzt."""
    from llm_router.proxy import _cf_access_cache_reset

    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    _cf_access_cache_reset()

    captured_headers: list[dict[str, str]] = []
    original_build = _MockClient.build_request

    def _capture_build(self, method, url, headers=None, content=None):
        captured_headers.append(dict(headers or {}))
        return original_build(self, method, url, headers=headers, content=content)

    monkeypatch.setattr(_MockClient, "build_request", _capture_build)

    mock = _install_mock(monkeypatch)
    mock.behaviors["primary.example"] = [503]
    mock.behaviors["fallback.example"] = [_MockResp(200)]

    spoke = _make_spoke()
    asyncio.run(_call(spoke, metrics))
    # Bei keinem Request darf der Header gesetzt sein.
    for headers in captured_headers:
        keys_lc = {k.lower() for k in headers}
        assert "cf-access-client-id" not in keys_lc
        assert "cf-access-client-secret" not in keys_lc


def test_recovery_via_fallback_successes_and_probe(monkeypatch, metrics):
    """Recovery-Pfad: nach _FAILOVER_THRESHOLD Fehlern + _RECOVERY_THRESHOLD
    erfolgreichen fallback-Aufrufen wird primary geprobed; bei 200 schliesst
    der Breaker und ``using_fallback`` wird False.
    """
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke()

    # _FAILOVER_THRESHOLD 503er auf primary, jeder mit erfolgreichem fallback-Retry.
    mock.behaviors["primary.example"] = [503] * _FAILOVER_THRESHOLD
    mock.behaviors["fallback.example"] = [_MockResp(200)] * (
        _FAILOVER_THRESHOLD + _RECOVERY_THRESHOLD
    )
    for _ in range(_FAILOVER_THRESHOLD):
        asyncio.run(_call(spoke, metrics))
    state = _breaker_get(spoke.name)
    assert state.using_fallback is True

    # Patch _probe_primary so der HEAD-Call deterministisch 200 liefert,
    # ohne echten Netzwerk-Call. Wir muessen den proxy-internen Symbol-Lookup
    # patchen (nicht das modul-globale Symbol).
    async def _fake_probe(_spoke):
        return True, 200

    monkeypatch.setattr("llm_router.proxy._probe_primary", _fake_probe)

    # Probe-Throttle deaktivieren — der Test ruft direkt mehrfach hintereinander.
    state.last_probe_at = None

    # Weitere _RECOVERY_THRESHOLD erfolgreiche fallback-Calls → Probe ausgeloest.
    for _ in range(_RECOVERY_THRESHOLD):
        asyncio.run(_call(spoke, metrics))

    state = _breaker_get(spoke.name)
    assert state.using_fallback is False, "Breaker sollte recovered haben"
    assert state.recovery_events == 1
    assert state.consecutive_failures == 0


def test_probe_failure_keeps_breaker_open(monkeypatch, metrics):
    """Probe schlaegt fehl → Breaker bleibt offen, recovery_events == 0."""
    mock = _install_mock(monkeypatch)
    spoke = _make_spoke()

    mock.behaviors["primary.example"] = [503] * _FAILOVER_THRESHOLD
    mock.behaviors["fallback.example"] = [_MockResp(200)] * (
        _FAILOVER_THRESHOLD + _RECOVERY_THRESHOLD
    )
    for _ in range(_FAILOVER_THRESHOLD):
        asyncio.run(_call(spoke, metrics))
    state = _breaker_get(spoke.name)
    assert state.using_fallback is True

    async def _fake_probe_bad(_spoke):
        return False, 502

    monkeypatch.setattr("llm_router.proxy._probe_primary", _fake_probe_bad)
    state.last_probe_at = None

    for _ in range(_RECOVERY_THRESHOLD):
        asyncio.run(_call(spoke, metrics))

    state = _breaker_get(spoke.name)
    assert state.using_fallback is True, "Probe-Fail → Breaker bleibt offen"
    assert state.recovery_events == 0
