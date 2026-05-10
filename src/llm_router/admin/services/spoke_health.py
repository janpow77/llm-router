"""Background-Task fuer periodische Spoke-Health-Checks.

Pingt alle aktivierten Spokes alle ``interval_s`` Sekunden, schreibt das
Ergebnis in ``admin_spokes.status``/``last_check_at``/``last_error`` und
loest bei Erfolg zusaetzlich Modell-Discovery aus.

Designed fuer ``asyncio.create_task`` aus dem FastAPI-Lifespan.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from ..db import get_session_factory
from ..models import SpokeRow
from . import model_discovery

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 30
DEFAULT_TIMEOUT_S = 5.0


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


async def _ping_spoke(spoke: SpokeRow, timeout_s: float = DEFAULT_TIMEOUT_S) -> tuple[str, str | None, list[dict] | None]:
    """Pingt einen einzelnen Spoke. Liefert ``(status, error, models_payload)``.

    ``models_payload`` ist die geparste Modell-Liste vom Endpoint (oder None).
    """
    base = (spoke.base_url or "").rstrip("/")
    if not base:
        return "offline", "no base_url", None

    if spoke.type == "openai":
        url = f"{base}/v1/models"
    else:
        url = f"{base}/api/tags"

    headers: dict[str, str] = {}
    if spoke.auth_header and spoke.auth_value:
        headers[spoke.auth_header] = spoke.auth_value

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            return "offline", f"HTTP {resp.status_code}", None
        try:
            data = resp.json()
        except ValueError:
            return "online", None, None
        return "online", None, _normalize_models(spoke.type, data)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
        return "offline", f"{type(exc).__name__}: {exc}"[:200], None
    except Exception as exc:
        log.warning("Spoke-Ping unexpected error %s: %s", spoke.name, exc)
        return "offline", str(exc)[:200], None


def _normalize_models(spoke_type: str, payload: dict) -> list[dict]:
    """Normalisiert die Modell-Antwort beider Schemas zu einer einheitlichen Liste."""
    if not isinstance(payload, dict):
        return []
    items: list[dict] = []
    if spoke_type == "openai":
        for entry in payload.get("data") or []:
            if not isinstance(entry, dict):
                continue
            items.append({"name": entry.get("id"), "raw": entry})
    else:  # ollama
        for entry in payload.get("models") or []:
            if not isinstance(entry, dict):
                continue
            details = entry.get("details") or {}
            size_bytes = entry.get("size") or 0
            items.append(
                {
                    "name": entry.get("name") or entry.get("model"),
                    "size_gb": round(size_bytes / 1024 ** 3, 2) if size_bytes else None,
                    "context_length": entry.get("context_length") or details.get("context_length"),
                    "quantization": details.get("quantization_level"),
                    "raw": entry,
                }
            )
    return [i for i in items if i.get("name")]


def check_spoke_sync(session: Session, spoke_id: str) -> SpokeRow | None:
    """Synchroner Wrapper fuer einen einzelnen Spoke-Check.

    Wird vom On-Demand-Endpoint ``POST /spokes/{id}/health-check`` benutzt.
    """
    spoke = session.get(SpokeRow, spoke_id)
    if spoke is None:
        return None
    status, error, models = asyncio.run(_ping_spoke(spoke))
    spoke.status = status
    spoke.last_check_at = _iso_now()
    spoke.last_error = error
    spoke.updated_at = _iso_now()
    if models:
        model_discovery.persist_models(session, spoke, models, commit=False)
    session.commit()
    session.refresh(spoke)
    return spoke


async def check_all_once(session_factory) -> int:
    """Ein Durchlauf — pingt alle aktiven Spokes parallel."""
    session: Session = session_factory()
    try:
        spokes: Iterable[SpokeRow] = session.query(SpokeRow).filter(SpokeRow.enabled == 1).all()
        spokes_list = list(spokes)
        if not spokes_list:
            return 0
        results = await asyncio.gather(*(_ping_spoke(s) for s in spokes_list), return_exceptions=True)
        for spoke, result in zip(spokes_list, results, strict=True):
            if isinstance(result, BaseException):
                spoke.status = "offline"
                spoke.last_error = f"{type(result).__name__}: {result}"[:200]
                spoke.last_check_at = _iso_now()
                spoke.updated_at = _iso_now()
                continue
            status, error, models = result
            spoke.status = status
            spoke.last_error = error
            spoke.last_check_at = _iso_now()
            spoke.updated_at = _iso_now()
            if models:
                model_discovery.persist_models(session, spoke, models, commit=False)
        session.commit()
        return len(spokes_list)
    finally:
        session.close()


async def health_loop(stop_event: asyncio.Event, interval_s: int = DEFAULT_INTERVAL_S) -> None:
    """Background-Loop. Verlaesst sich auf ``stop_event`` zum Beenden."""
    factory = get_session_factory()
    log.info("Spoke-Health-Loop startet (interval=%ds)", interval_s)
    # Erster Run sofort
    try:
        await check_all_once(factory)
    except Exception as exc:
        log.warning("Erster Spoke-Health-Check fehlgeschlagen: %s", exc)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            await check_all_once(factory)
        except Exception as exc:
            log.warning("Spoke-Health-Check-Iteration fehlgeschlagen: %s", exc)
    log.info("Spoke-Health-Loop beendet.")
