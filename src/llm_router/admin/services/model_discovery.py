"""Modell-Discovery: laedt verfuegbare Modelle von Ollama-/OpenAI-Spokes
und persistiert sie in ``admin_models``.

Wird sowohl vom Health-Loop (passiv) als auch vom Endpoint
``POST /admin/api/models/refresh`` (aktiv) aufgerufen.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from ..models import ModelRow, SpokeRow

log = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


async def _fetch_models_for_spoke(spoke: SpokeRow, timeout_s: float = 5.0) -> list[dict]:
    """Holt die Modell-Liste eines Spokes als normalisierte Dicts."""
    base = (spoke.base_url or "").rstrip("/")
    if not base:
        return []
    if spoke.type == "openai":
        url = f"{base}/v1/models"
    else:
        url = f"{base}/api/tags"
    headers: dict[str, str] = {}
    if spoke.auth_header and spoke.auth_value:
        headers[spoke.auth_header] = spoke.auth_value
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            return []
        data = r.json()
    except Exception as exc:
        log.info("Modell-Discovery fuer %s fehlgeschlagen: %s", spoke.name, exc)
        return []
    return _normalize(spoke.type, data)


def _normalize(spoke_type: str, payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    out: list[dict] = []
    if spoke_type == "openai":
        for entry in payload.get("data") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("id")
            if not name:
                continue
            out.append({"name": name, "size_gb": None, "context_length": None, "quantization": None})
    else:
        for entry in payload.get("models") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("model")
            if not name:
                continue
            details = entry.get("details") or {}
            size = entry.get("size") or 0
            out.append(
                {
                    "name": name,
                    "size_gb": round(size / 1024 ** 3, 2) if size else None,
                    "context_length": entry.get("context_length") or details.get("context_length"),
                    "quantization": details.get("quantization_level"),
                }
            )
    return out


def persist_models(session: Session, spoke: SpokeRow, models: list[dict], commit: bool = True) -> int:
    """Schreibt die Modelle eines Spokes in admin_models (replace strategy).

    Strategy: Pro Spoke alte Eintraege loeschen + neue einfuegen. Einfach, ausreichend
    fuer < 1000 Modelle pro Spoke.
    """
    session.query(ModelRow).filter(ModelRow.spoke_id == spoke.id).delete()
    inserted = 0
    seen_ids: set[str] = set()
    for m in models:
        name = m.get("name")
        if not name:
            continue
        row_id = f"{name}@{spoke.name}"
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        row = ModelRow(
            id=row_id,
            name=name,
            spoke_id=spoke.id,
            spoke_name=spoke.name,
            size_gb=m.get("size_gb"),
            context_length=m.get("context_length"),
            quantization=m.get("quantization"),
            discovered_at=_iso_now(),
        )
        session.add(row)
        inserted += 1
    if commit:
        session.commit()
    else:
        session.flush()
    return inserted


async def discover_all(session: Session) -> int:
    """Triggert die Discovery fuer alle aktiven Spokes."""
    spokes = session.query(SpokeRow).filter(SpokeRow.enabled == 1).all()
    if not spokes:
        return 0
    results = await asyncio.gather(*(_fetch_models_for_spoke(s) for s in spokes), return_exceptions=True)
    total = 0
    for spoke, result in zip(spokes, results, strict=True):
        if isinstance(result, BaseException):
            log.info("Discovery fuer %s schlug fehl: %s", spoke.name, result)
            continue
        total += persist_models(session, spoke, result, commit=False)
    session.commit()
    return total


async def discover_for_spoke(session: Session, spoke: SpokeRow) -> int:
    """Discovery fuer einen einzelnen Spoke (synchron-asynchron)."""
    models = await _fetch_models_for_spoke(spoke)
    return persist_models(session, spoke, models, commit=True)
