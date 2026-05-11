"""CRUD-Funktionen fuer Quotas (pro App)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import AppRow, QuotaConfig, QuotaOut, QuotaRow, QuotaUpdate
from ..services import audit_log


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def get_quota(session: Session, app_id: str) -> QuotaOut | None:
    """Liefert Limits + aktuelle Nutzung fuer eine App."""
    app = session.get(AppRow, app_id)
    if app is None:
        return None
    row = session.get(QuotaRow, app_id)
    if row is None:
        # Fallback auf App-Defaults
        return QuotaOut(
            app_id=app_id,
            limits=QuotaConfig(
                rpm=app.quota_rpm,
                concurrent=app.quota_concurrent,
                daily_tokens=app.quota_daily_tokens,
            ),
            current={"rpm": 0, "concurrent": 0, "daily_tokens": 0},
        )
    return QuotaOut(
        app_id=app_id,
        limits=QuotaConfig(rpm=row.rpm, concurrent=row.concurrent, daily_tokens=row.daily_tokens),
        current={
            "rpm": row.current_rpm,
            "concurrent": row.current_concurrent,
            "daily_tokens": row.current_daily_tokens,
        },
    )


def update_quota(session: Session, app_id: str, patch: QuotaUpdate, *, ip: str | None = None) -> QuotaOut | None:
    app = session.get(AppRow, app_id)
    if app is None:
        return None
    row = session.get(QuotaRow, app_id)
    before = {
        "rpm": (row.rpm if row else app.quota_rpm),
        "concurrent": (row.concurrent if row else app.quota_concurrent),
        "daily_tokens": (row.daily_tokens if row else app.quota_daily_tokens),
    }
    new_rpm = patch.rpm if patch.rpm is not None else before["rpm"]
    new_conc = patch.concurrent if patch.concurrent is not None else before["concurrent"]
    new_daily = patch.daily_tokens if patch.daily_tokens is not None else before["daily_tokens"]

    if row is None:
        row = QuotaRow(
            app_id=app_id,
            rpm=new_rpm,
            concurrent=new_conc,
            daily_tokens=new_daily,
            updated_at=_now_iso(),
        )
        session.add(row)
    else:
        row.rpm = new_rpm
        row.concurrent = new_conc
        row.daily_tokens = new_daily
        row.updated_at = _now_iso()

    # App-Defaults mitschreiben (single-source-of-truth)
    app.quota_rpm = new_rpm
    app.quota_concurrent = new_conc
    app.quota_daily_tokens = new_daily
    app.updated_at = _now_iso()

    audit_log.write_audit(
        session,
        action="quota.update",
        target=app_id,
        before=before,
        after={"rpm": new_rpm, "concurrent": new_conc, "daily_tokens": new_daily},
        ip=ip,
        commit=False,
    )
    session.commit()
    session.refresh(row)
    return get_quota(session, app_id)
