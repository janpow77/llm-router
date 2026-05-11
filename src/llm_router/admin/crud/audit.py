"""Audit-Log Read-API.

Schreiben passiert in ``services.audit_log``; hier nur Listing/Filter.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import AuditRow


def list_audit(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 200,
) -> list[AuditRow]:
    q = session.query(AuditRow)
    if actor:
        q = q.filter(AuditRow.actor == actor)
    if action:
        q = q.filter(AuditRow.action == action)
    if target:
        q = q.filter(AuditRow.target == target)
    if since:
        # Minimal-Validierung
        try:
            normalized = since
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            datetime.fromisoformat(normalized)
            q = q.filter(AuditRow.ts >= since)
        except ValueError:
            pass
    return q.order_by(AuditRow.ts.desc()).limit(max(1, min(limit, 2000))).all()
