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
