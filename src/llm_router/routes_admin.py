"""Admin-Routen für Stats, App-Übersicht, Logs.

Read-only — keine Mutation. Auth dafür leicht: Wenn wir später Caddy davorhängen,
fügen wir Basic-Auth dort hinzu. Heute: nur Tailscale-intern erreichbar.
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .deps import RouterContext, get_context
from .proxy import spoke_health

router = APIRouter(prefix="/admin", tags=["admin"])

_UI_PATH = Path(__file__).parent / "ui" / "index.html"


@router.get("/", response_class=HTMLResponse)
async def admin_ui() -> HTMLResponse:
    if _UI_PATH.exists():
        return HTMLResponse(content=_UI_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>llm-router</h1><p>UI nicht gefunden.</p>", status_code=500)


@router.get("/stats")
async def admin_stats(
    ctx: RouterContext = Depends(get_context),
    hours: int = Query(24, ge=1, le=720),
) -> dict:
    spokes = []
    for spoke in ctx.config.spokes:
        spokes.append(await spoke_health(spoke))

    return {
        "uptime_s": int(time.time() - ctx.started_at),
        "totals_24h": ctx.metrics.totals(hours=hours),
        "by_app": ctx.metrics.requests_per_app_last(hours=hours),
        "top_models": ctx.metrics.top_models(hours=hours, limit=10),
        "latency_buckets_1h": ctx.metrics.latency_buckets(hours=1),
        "rate_limit_state": ctx.limiter.stats(),
        "spokes": spokes,
        "version": ctx.config.server.version,
    }


@router.get("/apps")
async def admin_apps(ctx: RouterContext = Depends(get_context)) -> list[dict]:
    return [
        {
            "id": a.id,
            "description": a.description,
            "rate_limit_rpm": a.rate_limit_rpm,
            "max_concurrent": a.max_concurrent,
            "api_key_set": bool(a.api_key),
        }
        for a in ctx.config.apps
    ]


@router.get("/logs")
async def admin_logs(
    ctx: RouterContext = Depends(get_context),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return ctx.metrics.recent_logs(limit=limit)


@router.get("/spokes")
async def admin_spokes(ctx: RouterContext = Depends(get_context)) -> list[dict]:
    return [await spoke_health(s) for s in ctx.config.spokes]


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def prometheus_metrics(ctx: RouterContext = Depends(get_context)) -> str:
    """Minimaler Prometheus-Plaintext-Export."""
    totals = ctx.metrics.totals(hours=24)
    by_app = ctx.metrics.requests_per_app_last(hours=24)
    lines: list[str] = []

    lines.append("# HELP llm_router_requests_total Anzahl Requests in den letzten 24h")
    lines.append("# TYPE llm_router_requests_total counter")
    lines.append(f'llm_router_requests_total {totals.get("total", 0) or 0}')

    lines.append("# HELP llm_router_errors_total HTTP >=400 in den letzten 24h")
    lines.append("# TYPE llm_router_errors_total counter")
    lines.append(f'llm_router_errors_total {totals.get("errors", 0) or 0}')

    lines.append("# HELP llm_router_avg_duration_ms Durchschnittliche Latenz")
    lines.append("# TYPE llm_router_avg_duration_ms gauge")
    avg = totals.get("avg_ms") or 0
    lines.append(f"llm_router_avg_duration_ms {avg:.2f}")

    lines.append("# HELP llm_router_app_requests Requests pro App in 24h")
    lines.append("# TYPE llm_router_app_requests counter")
    for a in by_app:
        lines.append(f'llm_router_app_requests{{app="{a["app_id"]}"}} {a["n"]}')

    return "\n".join(lines) + "\n"


@router.delete("/logs/older-than-days/{days}")
async def admin_prune(days: int, ctx: RouterContext = Depends(get_context)) -> JSONResponse:
    """Manuelles Pruning. Reine Wartung — kein Auth."""
    if days < 1:
        return JSONResponse(status_code=400, content={"error": "days >= 1"})
    deleted = ctx.metrics.prune(days)
    return JSONResponse(content={"deleted": deleted})
