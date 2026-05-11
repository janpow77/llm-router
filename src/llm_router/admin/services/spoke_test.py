"""Test-Connection-Service fuer Provider-Endpoints.

Wird vom Admin-Endpoint ``POST /admin/api/spokes/test-connection`` benutzt
um BEVOR ein Spoke angelegt wird zu pruefen, ob ein externer Provider
(OpenAI/Anthropic/Mistral/...) erreichbar ist und ein gueltiges
``api-key`` akzeptiert.

Sicherheits-Hinweise:
- ``auth_value`` wird NIEMALS geloggt (auch nicht bei Fehlern).
- Werte werden nicht persistiert — der Endpoint hat keinen DB-Zugriff.
- Timeout: 5s gesamt (connect+read).
"""
from __future__ import annotations

import logging
import time

import httpx

from ..models import SpokeTestConnectionRequest, SpokeTestConnectionResponse

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_TEST_ENDPOINT = "/v1/models"
MAX_SAMPLE_MODELS = 5


def _extract_models(payload: object) -> list[str]:
    """Versucht, eine Modell-Liste aus typischen Provider-Antworten zu lesen.

    Unterstuetzte Schemas:
      - OpenAI:    ``{"data": [{"id": "..."}]}``
      - Anthropic: ``{"data": [{"id": "..."}]}``  (seit 2024)
      - Ollama:    ``{"models": [{"name": "..."}]}``
      - Gemini:    ``{"models": [{"name": "models/..."}]}``
      - generisch: list of dicts mit ``id``/``name``/``model``
    """
    if isinstance(payload, dict):
        for key in ("data", "models"):
            arr = payload.get(key)
            if isinstance(arr, list):
                return _names_from_list(arr)
    if isinstance(payload, list):
        return _names_from_list(payload)
    return []


def _names_from_list(arr: list) -> list[str]:
    out: list[str] = []
    for entry in arr:
        if isinstance(entry, dict):
            name = entry.get("id") or entry.get("name") or entry.get("model")
            if isinstance(name, str) and name:
                out.append(name)
        elif isinstance(entry, str):
            out.append(entry)
    return out


async def test_connection(
    payload: SpokeTestConnectionRequest,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> SpokeTestConnectionResponse:
    """Macht einen HTTP-GET gegen ``base_url + test_endpoint`` und parst die Antwort.

    Liefert NIE eine Exception — Fehler werden als ``ok=False`` mit
    ``error``-Feld zurueckgegeben. Auth-Values werden niemals geloggt.
    """
    base = payload.base_url.rstrip("/")
    endpoint = payload.test_endpoint or DEFAULT_TEST_ENDPOINT
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    url = f"{base}{endpoint}"

    headers: dict[str, str] = {"Accept": "application/json"}
    header_name = (payload.auth_header or "").strip()
    if header_name and payload.auth_value:
        headers[header_name] = payload.auth_value

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        return SpokeTestConnectionResponse(
            ok=False,
            error=f"connection failed: {type(exc).__name__}",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except httpx.ReadTimeout:
        return SpokeTestConnectionResponse(
            ok=False,
            error="timeout (5s)",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except httpx.HTTPError as exc:
        # Auth-Wert NICHT in Log/Response leaken.
        log.info("test-connection HTTP error for %s: %s", base, type(exc).__name__)
        return SpokeTestConnectionResponse(
            ok=False,
            error=f"http error: {type(exc).__name__}",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        log.info("test-connection unexpected error for %s: %s", base, type(exc).__name__)
        return SpokeTestConnectionResponse(
            ok=False,
            error=f"unexpected: {type(exc).__name__}",
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    latency_ms = int((time.monotonic() - started) * 1000)

    if resp.status_code >= 400:
        # Body kann sensible Daten enthalten — nur Status zurueckgeben.
        return SpokeTestConnectionResponse(
            ok=False,
            status=resp.status_code,
            error=f"HTTP {resp.status_code}",
            latency_ms=latency_ms,
        )

    models: list[str] = []
    try:
        data = resp.json()
    except ValueError:
        # 2xx ohne JSON-Body — zaehlt als OK (z.B. /health endpoints).
        return SpokeTestConnectionResponse(
            ok=True,
            status=resp.status_code,
            models_count=0,
            sample_models=[],
            latency_ms=latency_ms,
        )
    else:
        models = _extract_models(data)

    return SpokeTestConnectionResponse(
        ok=True,
        status=resp.status_code,
        models_count=len(models),
        sample_models=models[:MAX_SAMPLE_MODELS],
        latency_ms=latency_ms,
    )
