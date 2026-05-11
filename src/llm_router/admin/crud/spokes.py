"""CRUD-Funktionen fuer Spokes."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ModelRow, SpokeCreate, SpokeRegister, SpokeRow, SpokeUpdate
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
        "capabilities": _decode_list(row.capabilities, ["llm"]),
        "tags": _decode_list(row.tags, []),
        "priority": row.priority,
        "enabled": bool(row.enabled),
        "auth_header": row.auth_header,
        # Wert NICHT loggen, kann Secret enthalten
        "auth_value_set": bool(row.auth_value),
        "source": getattr(row, "source", None) or "manual",
        "version": getattr(row, "version", None),
        "fallback_url": getattr(row, "fallback_url", None),
    }


def _decode_list(raw: str | None, default: list) -> list:
    if not raw:
        return list(default)
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else list(default)
    except (TypeError, ValueError):
        return list(default)


def _encode_list(values: list | None) -> str | None:
    if values is None:
        return None
    return json.dumps(list(values))


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
        capabilities=_encode_list(payload.capabilities) or '["llm"]',
        tags=_encode_list(payload.tags) or "[]",
        priority=payload.priority,
        auth_header=payload.auth.header if payload.auth else None,
        auth_value=payload.auth.value if payload.auth else None,
        status="unknown",
        enabled=1 if payload.enabled else 0,
        created_at=now,
        updated_at=now,
        source="manual",
        fallback_url=payload.fallback_url,
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
    if patch.capabilities is not None:
        row.capabilities = _encode_list(patch.capabilities)
    if patch.tags is not None:
        row.tags = _encode_list(patch.tags)
    if patch.priority is not None:
        row.priority = patch.priority
    if patch.auth is not None:
        row.auth_header = patch.auth.header
        row.auth_value = patch.auth.value
    if patch.enabled is not None:
        row.enabled = 1 if patch.enabled else 0
    if patch.fallback_url is not None:
        # Leer-String entfernt das Fallback wieder.
        row.fallback_url = patch.fallback_url or None
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


def upsert_dynamic_spoke(
    session: Session,
    payload: SpokeRegister,
    *,
    ip: str | None = None,
) -> tuple[SpokeRow, bool]:
    """Legt einen dynamischen Spoke an oder aktualisiert ihn (idempotent).

    Liefert ``(row, created)``. ``created=True`` wenn neu angelegt.
    Setzt ``source='dynamic'`` und bumpt ``last_seen_at``. Wird der Spoke
    schon manuell verwaltet (``source='manual'``), bleibt die Quelle
    erhalten — wir aktualisieren nur Heartbeat und Discovery-Felder.
    """
    now = _now_iso()
    existing = get_spoke_by_name(session, payload.name)
    if existing is not None:
        before = _serialize_for_audit(existing)
        # Endpoint/Capabilities aktualisieren — Heartbeat bumpen.
        existing.base_url = payload.base_url
        if payload.type:
            existing.type = payload.type
        if payload.capabilities:
            existing.capabilities = _encode_list(payload.capabilities) or '["llm"]'
        if payload.tags is not None:
            existing.tags = _encode_list(payload.tags) or "[]"
        if payload.priority is not None:
            existing.priority = payload.priority
        if payload.version is not None:
            existing.version = payload.version
        if payload.fallback_url is not None:
            existing.fallback_url = payload.fallback_url or None
        if payload.gpu_info is not None:
            existing.gpu_info = json.dumps(payload.gpu_info.model_dump(exclude_none=True))
        existing.last_seen_at = now
        # Wenn schon offline und wieder gemeldet → online setzen.
        if existing.status == "offline":
            existing.status = "online"
            existing.last_error = None
        existing.updated_at = now
        # source bleibt unveraendert — User-Override moeglich.
        session.flush()
        audit_log.write_audit(
            session,
            action="spoke.register",
            target=existing.id,
            before=before,
            after=_serialize_for_audit(existing),
            ip=ip,
            commit=False,
        )
        session.commit()
        session.refresh(existing)
        return existing, False

    row = SpokeRow(
        id=_new_id(),
        name=payload.name,
        base_url=payload.base_url,
        type=payload.type,
        capabilities=_encode_list(payload.capabilities) or '["llm"]',
        tags=_encode_list(payload.tags) or "[]",
        priority=payload.priority,
        auth_header=None,
        auth_value=None,
        status="online",  # Heartbeat ist gerade eingetroffen → online.
        last_seen_at=now,
        enabled=1,
        created_at=now,
        updated_at=now,
        source="dynamic",
        version=payload.version,
        fallback_url=payload.fallback_url,
        gpu_info=json.dumps(payload.gpu_info.model_dump(exclude_none=True)) if payload.gpu_info else None,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError(f"Constraint-Verletzung: {exc.orig}") from exc

    audit_log.write_audit(
        session,
        action="spoke.register",
        target=row.id,
        before=None,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row, True


def bump_heartbeat(session: Session, spoke_id: str) -> SpokeRow | None:
    """Bumpt ``last_seen_at`` fuer einen Spoke. Schaltet bei Bedarf von
    'offline' zurueck auf 'online'. Liefert die Row, oder None wenn unbekannt.
    """
    row = get_spoke(session, spoke_id)
    if row is None:
        return None
    now = _now_iso()
    row.last_seen_at = now
    if row.status == "offline":
        row.status = "online"
        row.last_error = None
    row.updated_at = now
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
