"""Audit-Log-Service.

Schreibt jede mutierende Aktion in die ``admin_audit``-Tabelle.
Wird typischerweise direkt aus den CRUD-Funktionen aufgerufen.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditRow

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        log.warning("Audit-Serialisierung fehlgeschlagen: %s", exc)
        return json.dumps({"_error": "serialization_failed", "type": type(value).__name__})


def write_audit(
    session: Session,
    *,
    action: str,
    target: str | None = None,
    before: Any = None,
    after: Any = None,
    actor: str = "admin",
    ip: str | None = None,
    commit: bool = True,
) -> AuditRow:
    """Legt einen Audit-Eintrag an.

    ``commit=False`` falls der Aufrufer die Transaktion selbst kontrolliert.
    """
    row = AuditRow(
        id=f"aud_{uuid.uuid4().hex}",
        ts=_now_iso(),
        actor=actor,
        action=action,
        target=target,
        before=_serialize(before),
        after=_serialize(after),
        ip=ip,
    )
    session.add(row)
    if commit:
        session.commit()
    else:
        session.flush()
    return row
