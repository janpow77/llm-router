"""SQLAlchemy-Setup fuer das Admin-Backend.

- SQLite, eigene Datei (Default ``/data/admin.db``)
- Pfad ueberschreibbar via Env ``ADMIN_DB_PATH``
- Synchrone Sessions (kompatibel zur Workshop-Konvention)
- Migrationen werden idempotent beim Startup eingespielt
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_init_lock = threading.Lock()
_initialized = False
_current_db_url: str | None = None


def _resolve_db_url() -> str:
    """Bestimmt die DB-URL.

    Reihenfolge:
    1. Env ``ADMIN_DB_URL`` (vollwertige SQLAlchemy-URL, auch ``sqlite:///:memory:``)
    2. Env ``ADMIN_DB_PATH`` (Pfad zur SQLite-Datei)
    3. ``/data/admin.db`` (Container-Default)
    """
    if url := os.environ.get("ADMIN_DB_URL"):
        return url
    path = os.environ.get("ADMIN_DB_PATH", "/data/admin.db")
    return f"sqlite:///{path}"


def _ensure_parent_dir(db_url: str) -> None:
    """Erstellt das Eltern-Verzeichnis fuer SQLite-Dateipfade."""
    if db_url.startswith("sqlite:///") and ":memory:" not in db_url:
        path = Path(db_url.replace("sqlite:///", "", 1))
        if path.parent and not path.parent.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning("Konnte Eltern-Dir fuer Admin-DB nicht anlegen: %s (%s)", path.parent, exc)


def _build_engine(db_url: str) -> Engine:
    """Erzeugt eine SQLAlchemy-Engine mit sinnvollen SQLite-Defaults."""
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    eng = create_engine(
        db_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )

    if db_url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


def init_db(db_url: str | None = None, force: bool = False) -> Engine:
    """Initialisiert Engine + SessionFactory und spielt Migrationen ein.

    Idempotent — kann mehrfach aufgerufen werden. Tests koennen ``force=True``
    setzen, um die Engine zu rotieren (z.B. fuer In-Memory-DB).
    """
    global _engine, _SessionLocal, _initialized, _current_db_url
    with _init_lock:
        url = db_url or _resolve_db_url()
        if _initialized and not force and url == _current_db_url:
            return _engine  # type: ignore[return-value]

        _ensure_parent_dir(url)
        _engine = _build_engine(url)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
        _current_db_url = url
        _apply_migrations(_engine)
        _initialized = True
        log.info("Admin-DB initialisiert: %s", url)
        return _engine


def _apply_migrations(eng: Engine) -> None:
    """Spielt alle ``*.sql``-Dateien in ``migrations/`` aus.

    Idempotent durch Verwendung von ``CREATE TABLE IF NOT EXISTS``.
    """
    migration_dir = Path(__file__).parent / "migrations"
    if not migration_dir.exists():
        log.warning("Migration-Verzeichnis fehlt: %s", migration_dir)
        return
    files = sorted(migration_dir.glob("*.sql"))
    if not files:
        log.warning("Keine Migrations-Dateien gefunden in %s", migration_dir)
        return
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        for f in files:
            sql = f.read_text(encoding="utf-8")
            cur.executescript(sql)
        raw.commit()
    finally:
        raw.close()


def get_engine() -> Engine:
    if _engine is None:
        return init_db()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI-Dependency: liefert eine Session, schliesst sie am Ende."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


def reset_for_tests(db_url: str = "sqlite:///:memory:") -> Engine:
    """Helfer fuer Tests: legt eine neue DB an (z.B. in-memory) und gibt Engine zurueck."""
    return init_db(db_url=db_url, force=True)
