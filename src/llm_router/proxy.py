"""Streaming-Proxy für LLM-Requests.

Reicht Requests transparent an einen Spoke (z.B. Ollama) durch und parst
optional Token-Counts aus dem Response, ohne den Body zu modifizieren.

Phase 3: Auto-Failover. Wenn ein Spoke ``fallback_url`` gesetzt hat und die
primary 3x in Folge in einen Failure-State faellt (Timeout oder 502/503/504),
schaltet der Proxy temporaer auf den Fallback. Nach 5 erfolgreichen primary-
Calls wird der Circuit-Breaker zurueckgesetzt (siehe ``_breaker``).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from .config import SpokeConfig
from .metrics import MetricsStore, RequestRecord

log = logging.getLogger(__name__)

# HTTP-Status-Codes die das Failover triggern (Upstream-Probleme).
_FAILOVER_STATUS = {502, 503, 504}
# Schwellwerte fuer den Circuit-Breaker.
_FAILOVER_THRESHOLD = 3  # nach N aufeinanderfolgenden primary-Fails → fallback
_RECOVERY_THRESHOLD = 5  # nach M erfolgreichen primary-Calls → wieder primary
# Probe-Konfiguration: bevor wir den Breaker schliessen, testen wir primary
# mit einem leichten HEAD-Request. Wenn der innerhalb des Timeouts ein 2xx/3xx
# liefert, schalten wir zurueck und schreiben ``route.recovery``.
_PROBE_PATH = "/v1/models"
_PROBE_TIMEOUT_S = 2.0
# Mindestabstand zwischen zwei Probe-Versuchen pro Spoke (Sekunden) — verhindert
# Probe-Hammering aus parallelen Requests waehrend der Recovery-Phase.
_PROBE_MIN_INTERVAL_S = 5.0

# Header die nicht 1:1 weitergereicht werden (Hop-by-hop oder Auth)
_STRIP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
    "x-app-id",
    "x-api-key",
    "accept-encoding",
}
_STRIP_RESPONSE_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "content-encoding",
}


# ----------------------------- CF-Access-Header ----------------------------

# Cache fuer CF-Access-Service-Token-Header. Env-Vars werden einmal beim
# ersten Failover gelesen — Tests koennen ``_cf_access_cache_reset()`` rufen,
# um den Cache zu invalidieren. Siehe docs/fallback-cloudflare.md.
_cf_access_cache: dict[str, str] | None = None
_cf_access_lock = threading.Lock()


def _cf_access_cache_reset() -> None:
    """Setzt den CF-Access-Header-Cache zurueck (Tests + SIGHUP)."""
    global _cf_access_cache
    with _cf_access_lock:
        _cf_access_cache = None


def _cf_access_headers() -> dict[str, str]:
    """Liest ``CF_ACCESS_CLIENT_ID`` / ``CF_ACCESS_CLIENT_SECRET`` aus dem Env.

    Wenn beide Variablen gesetzt sind, liefert die Funktion die zwei
    Cloudflare-Access-Header (``CF-Access-Client-Id`` /
    ``CF-Access-Client-Secret``). Andernfalls ``{}`` — Tunnels ohne
    Access-Policy bleiben so funktionsfaehig.
    """
    global _cf_access_cache
    with _cf_access_lock:
        if _cf_access_cache is not None:
            return _cf_access_cache
        client_id = (os.environ.get("CF_ACCESS_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("CF_ACCESS_CLIENT_SECRET") or "").strip()
        headers: dict[str, str] = {}
        if client_id and client_secret:
            headers["CF-Access-Client-Id"] = client_id
            headers["CF-Access-Client-Secret"] = client_secret
            log.info("cf-access: service-token loaded (client_id=%s***)", client_id[:6])
        _cf_access_cache = headers
        return headers


@dataclass
class ProxyResult:
    response: StreamingResponse | JSONResponse
    duration_ms: int


@dataclass
class _BreakerState:
    """Per-Spoke Failover-Zaehler. Kein DB-Persist — reset bei Restart OK."""
    consecutive_failures: int = 0
    consecutive_successes: int = 0  # gezaehlt fuer Recovery (fallback-Successes)
    using_fallback: bool = False
    failover_events: int = 0
    last_failover_at: float | None = None
    # Recovery: nach _RECOVERY_THRESHOLD erfolgreichen fallback-Calls testet
    # der Proxy primary mit einem HEAD-Probe. last_probe_at verhindert,
    # dass parallele Requests gleichzeitig probieren.
    last_probe_at: float | None = None
    recovery_events: int = 0


# Globaler Memory-State pro Spoke-Name. Thread-safe (FastAPI/asyncio fuehrt
# Requests concurrent aus → wir nutzen einen Lock fuer die schreibenden Pfade).
_breaker_states: dict[str, _BreakerState] = {}
_breaker_lock = threading.Lock()


def _breaker_get(spoke_name: str) -> _BreakerState:
    with _breaker_lock:
        state = _breaker_states.get(spoke_name)
        if state is None:
            state = _BreakerState()
            _breaker_states[spoke_name] = state
        return state


def _breaker_reset_all() -> None:
    """Nur fuer Tests: setzt alle Counter zurueck."""
    with _breaker_lock:
        _breaker_states.clear()


def _audit_failover_event(
    *,
    spoke_name: str,
    primary_url: str,
    fallback_url: str,
    reason: str,
) -> None:
    """Schreibt ein Failover-Event in das Admin-Audit-Log. Best-Effort —
    Fehler werden geloggt, aber nicht propagiert (Proxy bleibt unabhaengig
    von der Admin-DB lebensfaehig).
    """
    try:
        from .admin.db import get_session_factory
        from .admin.services.audit_log import write_audit

        with get_session_factory()() as session:
            write_audit(
                session,
                action="route.failover",
                target=spoke_name,
                before={"primary": primary_url, "fallback": fallback_url},
                after={"reason": reason},
                actor="router",
                commit=True,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Audit fuer route.failover fehlgeschlagen: %s", exc)


def _audit_recovery_event(
    *,
    spoke_name: str,
    primary_url: str,
    fallback_url: str,
    probe_status: int | None,
) -> None:
    """Schreibt ein Recovery-Event (Probe erfolgreich → primary wieder aktiv)."""
    try:
        from .admin.db import get_session_factory
        from .admin.services.audit_log import write_audit

        with get_session_factory()() as session:
            write_audit(
                session,
                action="route.recovery",
                target=spoke_name,
                before={"fallback": fallback_url},
                after={"primary": primary_url, "probe_status": probe_status},
                actor="router",
                commit=True,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Audit fuer route.recovery fehlgeschlagen: %s", exc)


async def _probe_primary(spoke: SpokeConfig) -> tuple[bool, int | None]:
    """HEAD ``/v1/models`` gegen die primary-URL. Liefert ``(ok, status)``.

    Timeout: ``_PROBE_TIMEOUT_S``. Bei Verbindungsfehlern oder >=500: not ok.
    """
    base = (spoke.url or "").rstrip("/")
    url = f"{base}{_PROBE_PATH}"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            resp = await client.head(url)
        return resp.status_code < 500, resp.status_code
    except Exception as exc:  # noqa: BLE001
        log.debug("primary-probe fuer %s schlug fehl: %s", spoke.name, exc)
        return False, None


def _select_target_url(
    spoke: SpokeConfig,
) -> tuple[str, bool]:
    """Wahl zwischen primary und fallback basierend auf Breaker-State.

    Liefert ``(base_url, is_fallback)``.
    """
    if not spoke.fallback_url:
        return spoke.url, False
    state = _breaker_get(spoke.name)
    if state.using_fallback:
        return spoke.fallback_url, True
    return spoke.url, False


def _record_outcome(
    spoke: SpokeConfig,
    *,
    success: bool,
    used_fallback: bool,
    status_code: int | None,
    reason: str | None,
) -> bool:
    """Aktualisiert den Circuit-Breaker und schaltet ggf. um.

    - Treffer auf primary, success → reset counters; in fallback-Mode (direct
      primary-Hit aus Tests) nach M Erfolgen sofort Recovery.
    - Treffer auf primary, fail → consecutive_failures += 1; wenn >= N und
      fallback verfuegbar → using_fallback=True + ``route.failover`` Audit.
    - Treffer auf fallback, success → consecutive_successes += 1; bei
      >= _RECOVERY_THRESHOLD signalisiert die Funktion dem Caller, einen
      primary-Probe auszufuehren (Returnwert ``True``).
    - Treffer auf fallback, fail → consecutive_successes = 0, log warn.

    Liefert ``True`` wenn ein Recovery-Probe ausstehen sollte.
    """
    if not spoke.fallback_url:
        return False
    state = _breaker_get(spoke.name)
    pending_audit: tuple[str, str, str, str] | None = None
    probe_due = False
    with _breaker_lock:
        if used_fallback:
            if not success:
                state.consecutive_successes = 0
                log.warning(
                    "Fallback fuer Spoke %s lieferte ebenfalls Fehler (status=%s, reason=%s)",
                    spoke.name, status_code, reason,
                )
            else:
                state.consecutive_successes += 1
                if (
                    state.using_fallback
                    and state.consecutive_successes >= _RECOVERY_THRESHOLD
                ):
                    now = time.time()
                    if (
                        state.last_probe_at is None
                        or (now - state.last_probe_at) >= _PROBE_MIN_INTERVAL_S
                    ):
                        state.last_probe_at = now
                        probe_due = True
        elif success:
            state.consecutive_failures = 0
            state.consecutive_successes += 1
            if state.using_fallback and state.consecutive_successes >= _RECOVERY_THRESHOLD:
                # Direct-Hit auf primary in fallback-Mode (Tests setzen das
                # manuell). Recovery sofort ohne Probe.
                state.using_fallback = False
                state.consecutive_successes = 0
                log.info(
                    "Circuit-Breaker fuer %s zurueckgesetzt — primary wieder aktiv",
                    spoke.name,
                )
        else:
            state.consecutive_successes = 0
            state.consecutive_failures += 1
            if (
                not state.using_fallback
                and state.consecutive_failures >= _FAILOVER_THRESHOLD
            ):
                state.using_fallback = True
                state.failover_events += 1
                state.last_failover_at = time.time()
                # Recovery-Counter sauber starten.
                state.consecutive_successes = 0
                pending_audit = (
                    spoke.name,
                    spoke.url,
                    spoke.fallback_url,
                    reason or "primary_failures",
                )
                log.warning(
                    "Circuit-Breaker tripped fuer Spoke %s — schalte auf fallback (%s)",
                    spoke.name, spoke.fallback_url,
                )
    # Audit ausserhalb des Locks ausloesen (DB-Schreibvorgang).
    if pending_audit is not None:
        _audit_failover_event(
            spoke_name=pending_audit[0],
            primary_url=pending_audit[1],
            fallback_url=pending_audit[2],
            reason=pending_audit[3],
        )
    return probe_due


async def _maybe_recover(spoke: SpokeConfig) -> None:
    """Probe gegen primary; bei Erfolg schliesst Breaker + ``route.recovery``."""
    if not spoke.fallback_url:
        return
    ok, status_code = await _probe_primary(spoke)
    state = _breaker_get(spoke.name)
    if not ok:
        with _breaker_lock:
            state.consecutive_successes = 0
        return
    pending_recovery: tuple[str, str, str, int | None] | None = None
    with _breaker_lock:
        if state.using_fallback:
            state.using_fallback = False
            state.consecutive_failures = 0
            state.consecutive_successes = 0
            state.recovery_events += 1
            pending_recovery = (
                spoke.name,
                spoke.url,
                spoke.fallback_url,
                status_code,
            )
            log.info(
                "Circuit-Breaker fuer %s recovered — primary wieder aktiv (probe=%s)",
                spoke.name, status_code,
            )
    if pending_recovery is not None:
        _audit_recovery_event(
            spoke_name=pending_recovery[0],
            primary_url=pending_recovery[1],
            fallback_url=pending_recovery[2],
            probe_status=pending_recovery[3],
        )


def _filter_request_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS}


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _STRIP_RESPONSE_HEADERS}


async def _read_body(request_iter: AsyncIterator[bytes]) -> bytes:
    chunks: list[bytes] = []
    async for chunk in request_iter:
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_model_from_payload(body: bytes) -> str | None:
    if not body:
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, dict):
        m = data.get("model")
        if isinstance(m, str):
            return m
    return None


def _is_stream_request(body: bytes) -> bool:
    if not body:
        return False
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(data.get("stream"))


def _parse_ollama_usage(line: bytes) -> tuple[int | None, int | None]:
    """Extrahiert prompt_eval_count / eval_count aus einer Ollama-Stream-Zeile."""
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    return data.get("prompt_eval_count"), data.get("eval_count")


def _parse_openai_usage(line: bytes) -> tuple[int | None, int | None]:
    """Extrahiert usage aus OpenAI-SSE-Chunk (data: {...})."""
    text = line.strip()
    if not text.startswith(b"data:"):
        return None, None
    payload = text[5:].strip()
    if payload == b"[DONE]" or not payload:
        return None, None
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None
    usage = (data or {}).get("usage") or {}
    return usage.get("prompt_tokens"), usage.get("completion_tokens")


async def _send_request(
    *,
    base_url: str,
    method: str,
    upstream_path: str,
    query: str,
    fwd_headers: dict[str, str],
    body: bytes,
    timeout: httpx.Timeout,
) -> tuple[httpx.AsyncClient | None, httpx.Response | None, Exception | None, str]:
    """Sendet einen Request gegen ``base_url``. Liefert (client, resp, exc, url).

    Bei Verbindungsfehlern: client/resp None, exc gesetzt. Der Aufrufer ist
    verantwortlich fuer das Schliessen von client+resp im Erfolgsfall.
    """
    base = base_url.rstrip("/")
    url = f"{base}{upstream_path}"
    if query:
        url = f"{url}?{query}"
    client = httpx.AsyncClient(timeout=timeout)
    try:
        req = client.build_request(method, url, headers=fwd_headers, content=body)
        resp = await client.send(req, stream=True)
        return client, resp, None, url
    except Exception as exc:
        await client.aclose()
        return None, None, exc, url


async def proxy(
    *,
    method: str,
    spoke: SpokeConfig,
    upstream_path: str,
    headers: dict[str, str],
    body: bytes,
    query: str,
    app_id: str,
    metrics: MetricsStore,
    route_label: str,
    response_kind: str = "auto",  # auto | ollama | openai
) -> StreamingResponse | JSONResponse:
    """Proxiert eine Anfrage an einen Spoke und sammelt Stats.

    Phase 3: Wenn ``spoke.fallback_url`` gesetzt ist und der Circuit-Breaker
    fuer diesen Spoke offen ist (= using_fallback=True), wird direkt der
    Fallback genutzt. Schlaegt der primary-Aufruf mit Timeout/5xx fehl,
    versuchen wir EINMAL den fallback. Erfolge/Failures werden ueber
    ``_record_outcome`` in den Breaker eingespielt.
    """
    fwd_headers = _filter_request_headers(headers)
    is_stream = _is_stream_request(body)
    model = _extract_model_from_payload(body)

    started = time.monotonic()
    timeout = httpx.Timeout(connect=10.0, read=spoke.timeout_s, write=30.0, pool=30.0)

    # Initialer Endpoint (primary oder schon fallback wenn Breaker offen).
    target_url, used_fallback = _select_target_url(spoke)
    # Bei direkten fallback-Calls (Breaker offen) muessen CF-Access-Header
    # mitgeschickt werden, falls Env-Vars gesetzt sind. _cf_access_headers()
    # liefert {} wenn keine Service-Token vorhanden — Tunnels ohne Policy ok.
    initial_headers = dict(fwd_headers)
    if used_fallback:
        initial_headers.update(_cf_access_headers())
    client, resp, exc, request_url = await _send_request(
        base_url=target_url,
        method=method,
        upstream_path=upstream_path,
        query=query,
        fwd_headers=initial_headers,
        body=body,
        timeout=timeout,
    )

    # Failover-Logik bei Verbindungsfehler oder 5xx auf primary.
    def _is_failover_trigger(_exc: Exception | None, _resp: httpx.Response | None) -> bool:
        if _exc is not None:
            return True
        if _resp is not None and _resp.status_code in _FAILOVER_STATUS:
            return True
        return False

    if (
        spoke.fallback_url
        and not used_fallback
        and _is_failover_trigger(exc, resp)
    ):
        # Outcome auf primary loggen (Misserfolg).
        _record_outcome(
            spoke,
            success=False,
            used_fallback=False,
            status_code=(resp.status_code if resp is not None else None),
            reason=(str(exc)[:120] if exc else f"upstream_{resp.status_code if resp else 'err'}"),
        )
        # Aufraeumen primary
        if resp is not None:
            try:
                await resp.aclose()
            except Exception:  # noqa: BLE001
                pass
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
        log.info(
            "Failover-Retry fuer Spoke %s: primary=%s → fallback=%s",
            spoke.name, spoke.url, spoke.fallback_url,
        )
        # Retry gegen fallback inkl. CF-Access-Header.
        fb_headers = dict(fwd_headers)
        fb_headers.update(_cf_access_headers())
        client, resp, exc, request_url = await _send_request(
            base_url=spoke.fallback_url,
            method=method,
            upstream_path=upstream_path,
            query=query,
            fwd_headers=fb_headers,
            body=body,
            timeout=timeout,
        )
        used_fallback = True

    if exc is not None:
        duration = int((time.monotonic() - started) * 1000)
        log.warning("Spoke unreachable: %s (%s)", request_url, exc)
        _record_outcome(
            spoke,
            success=False,
            used_fallback=used_fallback,
            status_code=None,
            reason=str(exc)[:120],
        )
        metrics.record(
            RequestRecord(
                app_id=app_id,
                route=route_label,
                model=model,
                prompt_tokens=None,
                completion_tokens=None,
                duration_ms=duration,
                http_status=502,
                spoke=spoke.name,
                error=str(exc)[:200],
            )
        )
        return JSONResponse(
            status_code=502,
            content={"error": "Spoke unreachable", "detail": str(exc), "spoke": spoke.name},
        )
    assert client is not None and resp is not None  # for type narrowing

    out_headers = _filter_response_headers(resp.headers)
    out_headers["X-Llm-Spoke"] = spoke.name
    if used_fallback:
        out_headers["X-Llm-Failover"] = "1"

    if not is_stream:
        # Komplette Response einlesen, dann zurückgeben.
        body_bytes = await resp.aread()
        await resp.aclose()
        await client.aclose()
        duration = int((time.monotonic() - started) * 1000)

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        try:
            data = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict):
            prompt_tokens = data.get("prompt_eval_count") or (data.get("usage") or {}).get(
                "prompt_tokens"
            )
            completion_tokens = data.get("eval_count") or (data.get("usage") or {}).get(
                "completion_tokens"
            )

        # Outcome an den Breaker melden — success wenn <500 und nicht
        # in der Failover-Range.
        probe_due = _record_outcome(
            spoke,
            success=resp.status_code < 500,
            used_fallback=used_fallback,
            status_code=resp.status_code,
            reason=None if resp.status_code < 500 else f"upstream_{resp.status_code}",
        )
        if probe_due:
            await _maybe_recover(spoke)
        metrics.record(
            RequestRecord(
                app_id=app_id,
                route=route_label,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=duration,
                http_status=resp.status_code,
                spoke=spoke.name,
                error=None if resp.status_code < 400 else f"upstream {resp.status_code}",
            )
        )
        return StreamingResponse(
            iter([body_bytes]),
            status_code=resp.status_code,
            headers=out_headers,
            media_type=resp.headers.get("content-type"),
        )

    # Streaming-Variante: aiter_raw() weiterreichen, Tokens nebenbei zählen.
    async def stream_iter() -> AsyncIterator[bytes]:
        nonlocal prompt_tokens, completion_tokens, status_seen
        try:
            buffer = b""
            async for chunk in resp.aiter_raw():
                yield chunk
                # Token-Counts opportunistisch parsen
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    if response_kind in ("auto", "openai") and line.startswith(b"data:"):
                        p, c = _parse_openai_usage(line)
                    else:
                        p, c = _parse_ollama_usage(line)
                    if p is not None:
                        prompt_tokens = p
                    if c is not None:
                        completion_tokens = c
        finally:
            await resp.aclose()
            await client.aclose()
            duration = int((time.monotonic() - started) * 1000)
            probe_due = _record_outcome(
                spoke,
                success=status_seen < 500,
                used_fallback=used_fallback,
                status_code=status_seen,
                reason=None if status_seen < 500 else f"upstream_{status_seen}",
            )
            if probe_due:
                await _maybe_recover(spoke)
            metrics.record(
                RequestRecord(
                    app_id=app_id,
                    route=route_label,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_ms=duration,
                    http_status=status_seen,
                    spoke=spoke.name,
                    error=None if status_seen < 400 else f"upstream {status_seen}",
                )
            )

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    status_seen: int = resp.status_code

    return StreamingResponse(
        stream_iter(),
        status_code=resp.status_code,
        headers=out_headers,
        media_type=resp.headers.get("content-type"),
    )


async def spoke_health(spoke: SpokeConfig) -> dict[str, object]:
    """Pingt den Spoke (Ollama: /api/tags) — kurze Timeouts."""
    base = spoke.url.rstrip("/")
    if spoke.scheme in ("ollama", "auto"):
        endpoint = f"{base}/api/tags"
    else:
        endpoint = f"{base}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(endpoint)
        if r.status_code >= 400:
            return {"name": spoke.name, "url": spoke.url, "ok": False, "status": r.status_code}
        models: list[str] = []
        try:
            data = r.json()
            if isinstance(data, dict):
                if "models" in data and isinstance(data["models"], list):
                    models = [m.get("name") or m.get("model") or "" for m in data["models"] if isinstance(m, dict)]
                elif "data" in data and isinstance(data["data"], list):
                    models = [m.get("id") for m in data["data"] if isinstance(m, dict) and m.get("id")]
        except ValueError:
            pass
        return {
            "name": spoke.name,
            "url": spoke.url,
            "ok": True,
            "status": r.status_code,
            "models": [m for m in models if m],
        }
    except Exception as exc:
        return {"name": spoke.name, "url": spoke.url, "ok": False, "error": str(exc)[:160]}
