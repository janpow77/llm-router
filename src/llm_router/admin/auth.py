"""Auth fuer das Admin-Backend.

- Single-Admin-Passwort aus Env ``LLM_ROUTER_ADMIN_PASSWORD``
  (Default: ``admin``, mit Warn-Log)
- Login-Endpoint vergleicht via ``secrets.compare_digest``
- Erfolg: zufaelliger opaker Token (32 Bytes urlsafe) in ``admin_sessions``
  mit ``expires_at = now + SESSION_TTL_HOURS`` (Default 24h)
- Bearer-Header: ``Authorization: Bearer <token>``
- FastAPI-Dependency ``require_auth`` fuer alle geschuetzten Endpoints
- SSE-Sonderweg: Token via Query ``?token=...`` (Browser-EventSource kann keine Header)
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_session
from .models import SessionRow

log = logging.getLogger(__name__)

SESSION_TTL_HOURS = int(os.environ.get("LLM_ROUTER_SESSION_TTL_HOURS", "24"))


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _from_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def configured_password() -> str:
    """Liest das Admin-Passwort aus der Env. Warnt, wenn Default genutzt wird."""
    pw = os.environ.get("LLM_ROUTER_ADMIN_PASSWORD")
    if not pw:
        log.warning("LLM_ROUTER_ADMIN_PASSWORD nicht gesetzt — fallback 'admin' (NUR FUER LOKALE TESTS!)")
        return "admin"
    return pw


def verify_password(password: str) -> bool:
    expected = configured_password()
    return secrets.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def issue_token(session: Session, *, ip: str | None = None) -> tuple[str, datetime]:
    """Legt einen neuen Session-Token an und liefert ``(token, expires_at)``."""
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=SESSION_TTL_HOURS)
    row = SessionRow(
        token=token,
        actor="admin",
        created_at=_iso(now),
        expires_at=_iso(expires),
        last_seen_at=_iso(now),
        ip=ip,
    )
    session.add(row)
    session.commit()
    return token, expires


def revoke_token(session: Session, token: str) -> bool:
    row = session.get(SessionRow, token)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def lookup_session(session: Session, token: str) -> SessionRow | None:
    row = session.get(SessionRow, token)
    if row is None:
        return None
    try:
        expires = _from_iso(row.expires_at)
    except ValueError:
        return None
    if expires <= _now():
        # abgelaufen — sofort loeschen
        session.delete(row)
        session.commit()
        return None
    # last_seen aktualisieren (best-effort)
    row.last_seen_at = _iso(_now())
    session.commit()
    return row


def cleanup_expired(session: Session) -> int:
    """Loescht abgelaufene Sessions. Liefert Anzahl der geloeschten."""
    now_iso = _iso(_now())
    rows = session.query(SessionRow).filter(SessionRow.expires_at <= now_iso).all()
    n = 0
    for r in rows:
        session.delete(r)
        n += 1
    if n:
        session.commit()
    return n


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        if len(parts) == 1:
            return parts[0].strip()
    # Fallback fuer SSE / EventSource
    qp = request.query_params.get("token")
    if qp:
        return qp.strip()
    return None


def require_auth(request: Request, session: Session = Depends(get_session)) -> SessionRow:
    """FastAPI-Dependency — wirft 401 wenn nicht eingeloggt."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")
    row = lookup_session(session, token)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return row


def optional_auth(request: Request, session: Session = Depends(get_session)) -> SessionRow | None:
    """Liefert die Session, wenn vorhanden — wirft nicht."""
    token = _extract_token(request)
    if not token:
        return None
    return lookup_session(session, token)


def client_ip(request: Request) -> str | None:
    """Extrahiert die Client-IP (X-Forwarded-For oder Peer)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
