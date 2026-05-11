"""Heartbeat-Timeout-Service fuer dynamisch registrierte Spokes.

Background-Task der alle ``interval_s`` Sekunden prueft, ob dynamisch
registrierte Spokes (``source='dynamic'``) noch leben. Ohne Heartbeat fuer
``timeout_s`` Sekunden wird ``status`` auf ``offline`` gesetzt — der
Router-Core schliesst diese Spokes dann aus dem Routing aus.

Designed fuer ``asyncio.create_task`` aus dem FastAPI-Lifespan, analog zu
``spoke_health.health_loop``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from ..db import get_session_factory
from ..models import SpokeRow

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 60  # Pruef-Zyklus
DEFAULT_TIMEOUT_S = 90   # last_seen_at aelter → offline


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sweep_once(session_factory: sessionmaker, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> int:
    """Ein Durchlauf. Liefert die Anzahl der Spokes, die offline geschaltet wurden."""
    now = datetime.now(tz=UTC)
    transitioned = 0
    session = session_factory()
    try:
        rows = (
            session.query(SpokeRow)
            .filter(SpokeRow.source == "dynamic")
            .filter(SpokeRow.status != "offline")
            .all()
        )
        for row in rows:
            last_seen = _parse_iso(row.last_seen_at)
            if last_seen is None:
                # Nie gepingt → wenn aelter als Anlegen → offline.
                ref = _parse_iso(row.created_at) or now
            else:
                ref = last_seen
            if (now - ref).total_seconds() > timeout_s:
                row.status = "offline"
                row.last_error = f"heartbeat timeout (>{timeout_s}s)"
                row.updated_at = _iso_now()
                transitioned += 1
        if transitioned:
            session.commit()
            log.info("Heartbeat-Sweep: %d dynamische Spoke(s) auf offline gesetzt.", transitioned)
        return transitioned
    finally:
        session.close()


async def heartbeat_loop(
    stop_event: asyncio.Event,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> None:
    """Background-Loop. Beendet sich ueber ``stop_event``."""
    factory = get_session_factory()
    log.info(
        "Heartbeat-Sweep-Loop startet (interval=%ds, timeout=%ds)",
        interval_s, timeout_s,
    )
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            transitioned = sweep_once(factory, timeout_s=timeout_s)
            if transitioned:
                # Runtime-Config neu laden, damit das Routing offline-Spokes
                # ab dem naechsten Request ausschliesst.
                try:
                    from llm_router import runtime_config as rc
                    rc.reload_from_admin_db()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Reload-runtime_config nach Sweep fehlgeschlagen: %s", exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Heartbeat-Sweep-Iteration fehlgeschlagen: %s", exc)
    log.info("Heartbeat-Sweep-Loop beendet.")
