"""CRUD-Funktionen fuer Routing-Regeln (Model-Glob -> Spoke).

Hinweis: Heisst ``routes``, gemeint sind nicht HTTP-Routen, sondern
Routing-Regeln des Proxy-Cores.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import RouteCreate, RouteRow, RouteUpdate, SpokeRow
from ..services import audit_log


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return f"rt_{uuid.uuid4().hex}"


def _serialize_for_audit(row: RouteRow) -> dict:
    return {
        "id": row.id,
        "model_glob": row.model_glob,
        "spoke_id": row.spoke_id,
        "priority": row.priority,
        "enabled": bool(row.enabled),
    }


def list_routes(session: Session) -> list[tuple[RouteRow, str]]:
    """Liefert ``(route, spoke_name)``-Tupel sortiert nach priority ASC."""
    rows = (
        session.query(RouteRow, SpokeRow.name)
        .outerjoin(SpokeRow, SpokeRow.id == RouteRow.spoke_id)
        .order_by(RouteRow.priority.asc())
        .all()
    )
    return [(r, name or "?") for r, name in rows]


def get_route(session: Session, route_id: str) -> RouteRow | None:
    return session.get(RouteRow, route_id)


def get_spoke_name(session: Session, spoke_id: str) -> str:
    spoke = session.get(SpokeRow, spoke_id)
    return spoke.name if spoke else "?"


def create_route(session: Session, payload: RouteCreate, *, ip: str | None = None) -> RouteRow:
    spoke = session.get(SpokeRow, payload.spoke_id)
    if spoke is None:
        raise ValueError(f"Spoke {payload.spoke_id} unbekannt")
    now = _now_iso()
    row = RouteRow(
        id=_new_id(),
        model_glob=payload.model_glob,
        spoke_id=payload.spoke_id,
        priority=payload.priority,
        enabled=1 if payload.enabled else 0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    audit_log.write_audit(
        session,
        action="route.create",
        target=row.id,
        before=None,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def update_route(session: Session, route_id: str, patch: RouteUpdate, *, ip: str | None = None) -> RouteRow | None:
    row = get_route(session, route_id)
    if row is None:
        return None
    before = _serialize_for_audit(row)
    if patch.model_glob is not None:
        row.model_glob = patch.model_glob
    if patch.spoke_id is not None:
        spoke = session.get(SpokeRow, patch.spoke_id)
        if spoke is None:
            raise ValueError(f"Spoke {patch.spoke_id} unbekannt")
        row.spoke_id = patch.spoke_id
    if patch.priority is not None:
        row.priority = patch.priority
    if patch.enabled is not None:
        row.enabled = 1 if patch.enabled else 0
    row.updated_at = _now_iso()
    session.flush()
    audit_log.write_audit(
        session,
        action="route.update",
        target=row.id,
        before=before,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def delete_route(session: Session, route_id: str, *, ip: str | None = None) -> bool:
    row = get_route(session, route_id)
    if row is None:
        return False
    before = _serialize_for_audit(row)
    session.delete(row)
    audit_log.write_audit(
        session,
        action="route.delete",
        target=route_id,
        before=before,
        after=None,
        ip=ip,
        commit=False,
    )
    session.commit()
    return True
