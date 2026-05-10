"""CRUD-Funktionen fuer Apps."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import AppCreate, AppRow, AppUpdate, QuotaConfig, QuotaRow
from ..services import api_key as api_key_service
from ..services import audit_log


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    return f"app_{uuid.uuid4().hex}"


def _serialize_for_audit(row: AppRow) -> dict:
    try:
        allowed = json.loads(row.allowed_models or "[]")
    except json.JSONDecodeError:
        allowed = []
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "allowed_models": allowed,
        "quota": {
            "rpm": row.quota_rpm,
            "concurrent": row.quota_concurrent,
            "daily_tokens": row.quota_daily_tokens,
        },
        "enabled": bool(row.enabled),
    }


def list_apps(session: Session) -> list[AppRow]:
    return session.query(AppRow).order_by(AppRow.created_at.desc()).all()


def get_app(session: Session, app_id: str) -> AppRow | None:
    return session.get(AppRow, app_id)


def get_app_by_name(session: Session, name: str) -> AppRow | None:
    return session.query(AppRow).filter(AppRow.name == name).one_or_none()


def create_app(session: Session, payload: AppCreate, *, ip: str | None = None) -> tuple[AppRow, str]:
    """Legt eine neue App an.

    Returns: ``(row, plain_api_key)`` — der Klartext-Key wird **nur einmal** ausgegeben.
    """
    if get_app_by_name(session, payload.name) is not None:
        raise ValueError(f"App '{payload.name}' existiert bereits")

    plain_key = api_key_service.generate_api_key(payload.name)
    now = _now_iso()
    row = AppRow(
        id=_new_id(),
        name=payload.name,
        description=payload.description or "",
        api_key_hash=api_key_service.hash_api_key(plain_key),
        api_key_preview=api_key_service.preview(plain_key),
        allowed_models=json.dumps(payload.allowed_models),
        quota_rpm=payload.quota.rpm,
        quota_concurrent=payload.quota.concurrent,
        quota_daily_tokens=payload.quota.daily_tokens,
        enabled=1 if payload.enabled else 0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    # Quota-Spiegel
    quota_row = QuotaRow(
        app_id=row.id,
        rpm=payload.quota.rpm,
        concurrent=payload.quota.concurrent,
        daily_tokens=payload.quota.daily_tokens,
        updated_at=now,
    )
    session.add(quota_row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError(f"Constraint-Verletzung beim Anlegen: {exc.orig}") from exc

    audit_log.write_audit(
        session,
        action="app.create",
        target=row.id,
        before=None,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row, plain_key


def update_app(session: Session, app_id: str, patch: AppUpdate, *, ip: str | None = None) -> AppRow | None:
    row = get_app(session, app_id)
    if row is None:
        return None
    before = _serialize_for_audit(row)

    if patch.name is not None and patch.name != row.name:
        # Name-Konflikt pruefen
        clash = get_app_by_name(session, patch.name)
        if clash is not None and clash.id != row.id:
            raise ValueError(f"App '{patch.name}' existiert bereits")
        row.name = patch.name
    if patch.description is not None:
        row.description = patch.description
    if patch.allowed_models is not None:
        row.allowed_models = json.dumps(patch.allowed_models)
    if patch.quota is not None:
        row.quota_rpm = patch.quota.rpm
        row.quota_concurrent = patch.quota.concurrent
        row.quota_daily_tokens = patch.quota.daily_tokens
        # Quota-Mirror aktualisieren
        quota = session.get(QuotaRow, app_id)
        if quota is None:
            quota = QuotaRow(app_id=app_id, rpm=patch.quota.rpm, concurrent=patch.quota.concurrent,
                              daily_tokens=patch.quota.daily_tokens, updated_at=_now_iso())
            session.add(quota)
        else:
            quota.rpm = patch.quota.rpm
            quota.concurrent = patch.quota.concurrent
            quota.daily_tokens = patch.quota.daily_tokens
            quota.updated_at = _now_iso()
    if patch.enabled is not None:
        row.enabled = 1 if patch.enabled else 0

    row.updated_at = _now_iso()
    session.flush()
    audit_log.write_audit(
        session,
        action="app.update",
        target=row.id,
        before=before,
        after=_serialize_for_audit(row),
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def delete_app(session: Session, app_id: str, *, ip: str | None = None) -> bool:
    row = get_app(session, app_id)
    if row is None:
        return False
    before = _serialize_for_audit(row)
    session.delete(row)
    audit_log.write_audit(
        session,
        action="app.delete",
        target=app_id,
        before=before,
        after=None,
        ip=ip,
        commit=False,
    )
    session.commit()
    return True


def rotate_key(session: Session, app_id: str, *, ip: str | None = None) -> tuple[AppRow, str] | None:
    row = get_app(session, app_id)
    if row is None:
        return None
    new_plain = api_key_service.generate_api_key(row.name)
    before = {"api_key_preview": row.api_key_preview}
    row.api_key_hash = api_key_service.hash_api_key(new_plain)
    row.api_key_preview = api_key_service.preview(new_plain)
    row.updated_at = _now_iso()
    audit_log.write_audit(
        session,
        action="app.rotate_key",
        target=app_id,
        before=before,
        after={"api_key_preview": row.api_key_preview},
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row, new_plain


def toggle_enabled(session: Session, app_id: str, *, ip: str | None = None) -> AppRow | None:
    row = get_app(session, app_id)
    if row is None:
        return None
    before = {"enabled": bool(row.enabled)}
    row.enabled = 0 if row.enabled else 1
    row.updated_at = _now_iso()
    audit_log.write_audit(
        session,
        action="app.toggle_enabled",
        target=app_id,
        before=before,
        after={"enabled": bool(row.enabled)},
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return row


def find_by_api_key(session: Session, plain: str) -> AppRow | None:
    """Sucht eine App per Klartext-Key (vergleicht Hash). Fuer Proxy-Auth."""
    if not plain:
        return None
    h = api_key_service.hash_api_key(plain)
    return session.query(AppRow).filter(AppRow.api_key_hash == h).one_or_none()
