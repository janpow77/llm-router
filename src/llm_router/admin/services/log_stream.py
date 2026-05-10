"""Live-Log-Stream via SSE.

Liest aus der Router-Core-Metrics-DB (`metrics.db`, vom MetricsStore gepflegt)
per Polling alle ``poll_s`` Sekunden, sendet neue Eintraege als SSE-Events.

Wird ueber den Endpoint ``GET /admin/api/logs/stream`` benutzt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_POLL_S = 2.0


def _resolve_metrics_db() -> Path | None:
    """Findet die metrics.db. Reihenfolge:
    1. ``METRICS_DB_PATH``
    2. ``/data/metrics.db``
    3. ``./metrics.db``
    """
    candidates: list[Path] = []
    if env := os.environ.get("METRICS_DB_PATH"):
        candidates.append(Path(env))
    candidates.append(Path("/data/metrics.db"))
    candidates.append(Path("metrics.db"))
    for c in candidates:
        if c.exists():
            return c
    return None


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=2.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_event(row: sqlite3.Row) -> dict:
    return {
        "ts": row["ts"],
        "request_id": f"req_{row['id']}",
        "app_id": row["app_id"],
        "model": row["model"],
        "spoke_id": row["spoke"],
        "status": "ok" if (row["http_status"] or 0) < 400 else "error",
        "http_status": row["http_status"],
        "duration_ms": row["duration_ms"],
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "error": row["error"],
        "route": row["route"],
    }


def _max_id(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS mx FROM requests").fetchone()
        return int(row["mx"] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0


def _fetch_after(conn: sqlite3.Connection, after_id: int, limit: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, ts, app_id, route, model, prompt_tokens, completion_tokens,
                  duration_ms, http_status, spoke, error
           FROM requests WHERE id > ? ORDER BY id ASC LIMIT ?""",
        (after_id, limit),
    ).fetchall()


async def stream_events(poll_s: float = DEFAULT_POLL_S, max_idle_s: float = 600.0) -> AsyncIterator[bytes]:
    """Generator fuer SSE-Bytes. Schliesst nach ``max_idle_s`` ohne Daten."""
    metrics_path = _resolve_metrics_db()
    if metrics_path is None:
        # Soft-Fail: einmalig hint senden, dann beenden
        payload = {"_warning": "metrics.db not found", "checked": ["METRICS_DB_PATH", "/data/metrics.db", "./metrics.db"]}
        yield f"event: warning\ndata: {json.dumps(payload)}\n\n".encode()
        return

    last_id = 0
    last_data_at = time.monotonic()
    yield b": connected\n\n"

    try:
        conn = _connect(metrics_path)
    except sqlite3.Error as exc:
        yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n".encode()
        return

    try:
        last_id = _max_id(conn)
        while True:
            await asyncio.sleep(poll_s)
            try:
                rows = _fetch_after(conn, last_id)
            except sqlite3.Error as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n".encode()
                await asyncio.sleep(poll_s)
                continue
            if rows:
                last_data_at = time.monotonic()
                for r in rows:
                    last_id = max(last_id, int(r["id"]))
                    payload = _row_to_event(r)
                    yield f"data: {json.dumps(payload)}\n\n".encode()
            else:
                # Keepalive-Kommentar alle 15s
                if time.monotonic() - last_data_at >= 15:
                    yield b": keepalive\n\n"
                    last_data_at = time.monotonic()
            if time.monotonic() - last_data_at > max_idle_s:
                yield b": idle-timeout\n\n"
                break
    finally:
        try:
            conn.close()
        except Exception:
            pass


def read_recent(
    *,
    app_id: str | None = None,
    model: str | None = None,
    status: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Liest die letzten Eintraege aus metrics.db (Best-Effort)."""
    path = _resolve_metrics_db()
    if path is None:
        return []
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return []
    try:
        clauses: list[str] = []
        params: list = []
        if app_id:
            clauses.append("app_id = ?")
            params.append(app_id)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if status == "ok":
            clauses.append("http_status < 400")
        elif status == "error":
            clauses.append("http_status >= 400")
        if since:
            try:
                # ISO-Datum -> epoch
                from datetime import datetime
                if since.endswith("Z"):
                    since = since[:-1] + "+00:00"
                ts = datetime.fromisoformat(since).timestamp()
                clauses.append("ts >= ?")
                params.append(ts)
            except ValueError:
                pass
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, ts, app_id, route, model, prompt_tokens, completion_tokens, "
            "duration_ms, http_status, spoke, error "
            f"FROM requests {where} ORDER BY id DESC LIMIT ?"
        )
        params.append(int(limit))
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        return [_row_to_event(r) for r in rows]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def aggregate_dashboard(hours: int = 24) -> dict:
    """Aggregiert Stats aus metrics.db fuer das Dashboard."""
    path = _resolve_metrics_db()
    if path is None:
        return _empty_dashboard()
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return _empty_dashboard()
    try:
        cutoff = time.time() - hours * 3600
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          AVG(duration_ms) AS avg_ms,
                          SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) AS errors,
                          SUM(COALESCE(prompt_tokens, 0)) AS pt,
                          SUM(COALESCE(completion_tokens, 0)) AS ct
                   FROM requests WHERE ts >= ?""",
                (cutoff,),
            ).fetchone()
            durations = [
                int(r["duration_ms"])
                for r in conn.execute(
                    "SELECT duration_ms FROM requests WHERE ts >= ? ORDER BY duration_ms",
                    (cutoff,),
                ).fetchall()
            ]
            top_apps = [
                {"app_id": r["app_id"], "name": r["app_id"], "count": int(r["n"])}
                for r in conn.execute(
                    "SELECT app_id, COUNT(*) AS n FROM requests WHERE ts >= ? GROUP BY app_id ORDER BY n DESC LIMIT 10",
                    (cutoff,),
                ).fetchall()
            ]
            top_models = [
                {"model": r["model"], "count": int(r["n"])}
                for r in conn.execute(
                    "SELECT model, COUNT(*) AS n FROM requests WHERE ts >= ? AND model IS NOT NULL "
                    "GROUP BY model ORDER BY n DESC LIMIT 10",
                    (cutoff,),
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            return _empty_dashboard()

        total = int(row["total"] or 0)
        mean_ms = float(row["avg_ms"] or 0.0)
        errors = int(row["errors"] or 0)
        prompt_tokens = int(row["pt"] or 0)
        completion_tokens = int(row["ct"] or 0)

        p95 = _percentile(durations, 95) if durations else 0
        return {
            "requests_today": total,
            "tokens_today": prompt_tokens + completion_tokens,
            "errors_today": errors,
            "mean_latency_ms": int(mean_ms),
            "p95_latency_ms": int(p95),
            "top_apps": top_apps,
            "top_models": top_models,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def aggregate_timeseries(bucket: str = "1h", hours: int = 24) -> list[dict]:
    """Liefert Zeitreihen-Buckets fuer das Chart."""
    path = _resolve_metrics_db()
    if path is None:
        return []
    bucket_seconds = {"5m": 300, "15m": 900, "1h": 3600}.get(bucket, 3600)
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return []
    try:
        cutoff = time.time() - hours * 3600
        try:
            rows = conn.execute(
                f"""SELECT (CAST(ts / {bucket_seconds} AS INTEGER) * {bucket_seconds}) AS slot,
                           COUNT(*) AS n,
                           AVG(duration_ms) AS avg_ms,
                           SUM(CASE WHEN http_status >= 400 THEN 1 ELSE 0 END) AS errors,
                           SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)) AS tokens
                    FROM requests
                    WHERE ts >= ?
                    GROUP BY slot ORDER BY slot ASC""",
                (cutoff,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        out = []
        from datetime import UTC, datetime
        for r in rows:
            slot = int(r["slot"] or 0)
            iso = datetime.fromtimestamp(slot, tz=UTC).isoformat().replace("+00:00", "Z")
            out.append(
                {
                    "ts": iso,
                    "requests": int(r["n"] or 0),
                    "tokens": int(r["tokens"] or 0),
                    "errors": int(r["errors"] or 0),
                    "mean_latency_ms": int(r["avg_ms"] or 0),
                }
            )
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass


def app_request_counts_today() -> dict[str, int]:
    """Liefert {app_id: count} fuer die letzten 24h."""
    path = _resolve_metrics_db()
    if path is None:
        return {}
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return {}
    try:
        cutoff = time.time() - 24 * 3600
        try:
            rows = conn.execute(
                "SELECT app_id, COUNT(*) AS n FROM requests WHERE ts >= ? GROUP BY app_id",
                (cutoff,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["app_id"]: int(r["n"]) for r in rows}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def app_recent_requests(app_id: str, limit: int = 50) -> list[dict]:
    return read_recent(app_id=app_id, limit=limit)


def _percentile(sorted_values: list[int], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _empty_dashboard() -> dict:
    return {
        "requests_today": 0,
        "tokens_today": 0,
        "errors_today": 0,
        "mean_latency_ms": 0,
        "p95_latency_ms": 0,
        "top_apps": [],
        "top_models": [],
    }
