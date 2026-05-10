"""SQLite-basierte Metrics-Sammlung für llm-router.

Wir speichern pro Request:
    - timestamp (epoch seconds, float)
    - app_id
    - route (HTTP-Pfad)
    - model
    - prompt_tokens, completion_tokens (None wenn Upstream nichts liefert)
    - duration_ms
    - http_status
    - spoke (Name des Backends)
    - error (kurzer String wenn fehlgeschlagen)

Schreibt in eine SQLite-DB, mit WAL-Modus für gleichzeitiges Lesen vom UI.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    app_id          TEXT NOT NULL,
    route           TEXT NOT NULL,
    model           TEXT,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    duration_ms     INTEGER NOT NULL,
    http_status     INTEGER NOT NULL,
    spoke           TEXT,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_app ON requests(app_id, ts);
CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model, ts);
"""


@dataclass
class RequestRecord:
    app_id: str
    route: str
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ms: int
    http_status: int
    spoke: str | None = None
    error: str | None = None
    ts: float | None = None


class MetricsStore:
    """Thread-safer SQLite-Wrapper. Schreibvorgänge sind kurz; Reader sind WAL."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def record(self, rec: RequestRecord) -> None:
        ts = rec.ts if rec.ts is not None else time.time()
        try:
            with self._lock, self._conn() as conn:
                conn.execute(
                    """INSERT INTO requests
                    (ts, app_id, route, model, prompt_tokens, completion_tokens,
                     duration_ms, http_status, spoke, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ts,
                        rec.app_id,
                        rec.route,
                        rec.model,
                        rec.prompt_tokens,
                        rec.completion_tokens,
                        rec.duration_ms,
                        rec.http_status,
                        rec.spoke,
                        rec.error,
                    ),
                )
        except Exception as exc:
            log.warning("Metrics-Insert fehlgeschlagen: %s", exc)

    # ---- Aggregations ----

    def requests_per_app_last(self, hours: int = 24) -> list[dict[str, Any]]:
        cutoff = time.time() - hours * 3600
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT app_id, COUNT(*) AS n,
                          AVG(duration_ms) AS avg_ms,
                          SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) AS errors
                   FROM requests WHERE ts >= ?
                   GROUP BY app_id ORDER BY n DESC""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def top_models(self, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
        cutoff = time.time() - hours * 3600
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT model, COUNT(*) AS n, AVG(duration_ms) AS avg_ms
                   FROM requests WHERE ts >= ? AND model IS NOT NULL
                   GROUP BY model ORDER BY n DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def latency_buckets(self, hours: int = 1) -> list[dict[str, Any]]:
        """Gibt Latenz-Histogramm in fixen Buckets zurück.

        Buckets: <100ms, 100–500ms, 500ms–2s, 2–10s, 10–60s, >60s
        """
        cutoff = time.time() - hours * 3600
        buckets = [
            ("<100ms", 0, 100),
            ("100-500ms", 100, 500),
            ("500ms-2s", 500, 2000),
            ("2-10s", 2000, 10000),
            ("10-60s", 10000, 60000),
            (">60s", 60000, 10**12),
        ]
        result = []
        with self._conn() as conn:
            for label, lo, hi in buckets:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM requests WHERE ts >= ? AND duration_ms >= ? AND duration_ms < ?",
                    (cutoff, lo, hi),
                ).fetchone()
                result.append({"label": label, "count": row["n"]})
        return result

    def recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, ts, app_id, route, model, duration_ms, http_status, spoke, error
                   FROM requests ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def totals(self, hours: int = 24) -> dict[str, Any]:
        cutoff = time.time() - hours * 3600
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          AVG(duration_ms) AS avg_ms,
                          SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) AS errors,
                          SUM(COALESCE(prompt_tokens, 0)) AS prompt_tokens,
                          SUM(COALESCE(completion_tokens, 0)) AS completion_tokens
                   FROM requests WHERE ts >= ?""",
                (cutoff,),
            ).fetchone()
        return dict(row) if row else {}

    def prune(self, retention_days: int) -> int:
        cutoff = time.time() - retention_days * 86400
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM requests WHERE ts < ?", (cutoff,))
            return cur.rowcount or 0
