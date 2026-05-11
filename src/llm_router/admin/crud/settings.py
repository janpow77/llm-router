"""CRUD-Funktionen fuer Settings (Key-Value-Store)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import QuotaConfig, SettingRow

DEFAULTS: dict[str, Any] = {
    "log_retention_days": 30,
    "default_quotas": {"rpm": 60, "concurrent": 4, "daily_tokens": 1_000_000},
    "spoke_health_interval_s": 30,
}


def get_all(session: Session) -> dict[str, Any]:
    rows = session.query(SettingRow).all()
    out = dict(DEFAULTS)
    for r in rows:
        try:
            out[r.key] = json.loads(r.value)
        except json.JSONDecodeError:
            out[r.key] = r.value
    return out


def get_value(session: Session, key: str) -> Any:
    row = session.get(SettingRow, key)
    if row is None:
        return DEFAULTS.get(key)
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return row.value


def set_value(session: Session, key: str, value: Any, *, commit: bool = True) -> None:
    row = session.get(SettingRow, key)
    payload = json.dumps(value, ensure_ascii=False, default=str)
    if row is None:
        row = SettingRow(key=key, value=payload)
        session.add(row)
    else:
        row.value = payload
    if commit:
        session.commit()
    else:
        session.flush()


def update_partial(session: Session, patch: dict[str, Any]) -> dict[str, Any]:
    for k, v in patch.items():
        if v is None:
            continue
        if isinstance(v, QuotaConfig):
            v = v.model_dump()
        set_value(session, k, v, commit=False)
    session.commit()
    return get_all(session)
