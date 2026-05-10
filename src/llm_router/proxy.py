"""Streaming-Proxy für LLM-Requests.

Reicht Requests transparent an einen Spoke (z.B. Ollama) durch und parst
optional Token-Counts aus dem Response, ohne den Body zu modifizieren.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

from .config import SpokeConfig
from .metrics import MetricsStore, RequestRecord

log = logging.getLogger(__name__)

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


@dataclass
class ProxyResult:
    response: StreamingResponse | JSONResponse
    duration_ms: int


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
    """Proxiert eine Anfrage an einen Spoke und sammelt Stats."""
    base = spoke.url.rstrip("/")
    url = f"{base}{upstream_path}"
    if query:
        url = f"{url}?{query}"

    fwd_headers = _filter_request_headers(headers)
    is_stream = _is_stream_request(body)
    model = _extract_model_from_payload(body)

    started = time.monotonic()
    timeout = httpx.Timeout(connect=10.0, read=spoke.timeout_s, write=30.0, pool=30.0)
    client = httpx.AsyncClient(timeout=timeout)

    try:
        req = client.build_request(method, url, headers=fwd_headers, content=body)
        resp = await client.send(req, stream=True)
    except Exception as exc:
        await client.aclose()
        duration = int((time.monotonic() - started) * 1000)
        log.warning("Spoke unreachable: %s (%s)", url, exc)
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

    out_headers = _filter_response_headers(resp.headers)
    out_headers["X-Llm-Spoke"] = spoke.name

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
