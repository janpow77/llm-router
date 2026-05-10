"""CRUD-Funktionen fuer Spokes."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ModelRow, SpokeCreate, SpokeRow, SpokeUpdate
from ..services import audit_log


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return f"spk_{uuid.uuid4().hex}"


def _serialize_for_audit(row: SpokeRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "base_url": row.base_url,
        "type": row.type,
        "enabled": bool(row.enabled),
        "auth_header": row.auth_header,
        # Wert NICHT loggen, kann Secret enthalten
        "auth_value_set": bool(row.auth_value),
    }


def list_spokes(session: Session) -> list[SpokeRow]:
    return session.query(SpokeRow).order_by(SpokeRow.created_at.asc()).all()


def get_spoke(session: Session, spoke_id: str) -> SpokeRow | None:
    return session.get(SpokeRow, spoke_id)


def get_spoke_by_name(session: Session, name: str) -> SpokeRow | None:
    return session.query(SpokeRow).filter(SpokeRow.name == name).one_or_none()


def list_models_for_spoke(session: Session, spoke_id: str) -> list[str]:
    rows = session.query(ModelRow).filter(ModelRow.spoke_id == spoke_id).all()
    return [r.name for r in rows]


def create_spoke(session: Session, payload: SpokeCreate, *, ip: str | None = None) -> SpokeRow:
    if get_spoke_by_name(session, payload.name):
        raise ValueError(f"Spoke '{payload.name}' existiert bereits")
    now = _now_iso()
    row = SpokeRow(
        id=_new_id(),
        name=payload.name,
        base_url=payload.base_url,
        type=payload.type,
        auth_header=payload.auth.header if payload.auth else None,
        auth_value=payload.auth.value if payload.auth else None,
        status="unknown",
        enabled=1 if payload.enabled else 0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError(f"Constraint-Verletzung: {exc.orig}") from exc

    audit_log.write_audit(
        session,
        action="spoke.create",
        target=row.id,
        before=None,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def update_spoke(session: Session, spoke_id: str, patch: SpokeUpdate, *, ip: str | None = None) -> SpokeRow | None:
    row = get_spoke(session, spoke_id)
    if row is None:
        return None
    before = _serialize_for_audit(row)

    if patch.name is not None and patch.name != row.name:
        clash = get_spoke_by_name(session, patch.name)
        if clash is not None and clash.id != row.id:
            raise ValueError(f"Spoke '{patch.name}' existiert bereits")
        row.name = patch.name
    if patch.base_url is not None:
        row.base_url = patch.base_url.rstrip("/")
    if patch.type is not None:
        row.type = patch.type
    if patch.auth is not None:
        row.auth_header = patch.auth.header
        row.auth_value = patch.auth.value
    if patch.enabled is not None:
        row.enabled = 1 if patch.enabled else 0
    row.updated_at = _now_iso()
    session.flush()

    audit_log.write_audit(
        session,
        action="spoke.update",
        target=row.id,
        before=before,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def delete_spoke(session: Session, spoke_id: str, *, ip: str | None = None) -> bool:
    row = get_spoke(session, spoke_id)
    if row is None:
        return False
    before = _serialize_for_audit(row)
    session.delete(row)
    audit_log.write_audit(
        session,
        action="spoke.delete",
        target=spoke_id,
        before=before,
        after=None,
        ip=ip,
        commit=False,
    )
    session.commit()
    return True
