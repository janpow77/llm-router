"""FastAPI-App für llm-router.

Routing-Hub: empfängt Ollama- und OpenAI-kompatible Requests, identifiziert
die Quell-App über X-App-Id, prüft Rate-Limits und proxt an einen GPU-Spoke.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from . import __version__
from .config import load_config
from .deps import RouterContext
from .metrics import MetricsStore
from .proxy import spoke_health
from .ratelimit import RateLimiter
from .routes_admin import router as admin_router
from .routes_ollama import router as ollama_router
from .routes_openai import router as openai_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("llm_router")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    config.server.version = __version__
    metrics = MetricsStore(config.metrics.db_path)
    limiter = RateLimiter()
    ctx = RouterContext(config=config, metrics=metrics, limiter=limiter, started_at=time.time())
    app.state.ctx = ctx
    log.info(
        "llm-router %s gestartet — %d apps, %d spokes, db=%s",
        __version__,
        len(config.apps),
        len(config.spokes),
        config.metrics.db_path,
    )
    yield
    log.info("llm-router stoppt.")


app = FastAPI(
    title="llm-router",
    version=__version__,
    description="Zentraler LLM-Routing-Hub für Workshop, audit_designer, flowinvoice etc.",
    lifespan=lifespan,
)

# CORS — bewusst offen, da Tailscale-intern. Falls extern via Caddy: dort
# einschränken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Llm-Spoke"],
)


@app.middleware("http")
async def release_rate_limit(request: Request, call_next):
    """Stellt sicher, dass jeder Rate-Limit-Slot wieder freigegeben wird."""
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        ctx: RouterContext | None = getattr(request.app.state, "ctx", None)
        app_id = getattr(request.state, "app_id", None)
        acquired = getattr(request.state, "app_acquired", False)
        if ctx and app_id and acquired:
            await ctx.limiter.release(app_id)


@app.get("/health")
async def health(request: Request):
    ctx: RouterContext = request.app.state.ctx
    spokes = []
    for spoke in ctx.config.spokes:
        spokes.append(await spoke_health(spoke))
    overall = all(s.get("ok") for s in spokes) if spokes else False
    return {
        "status": "ok" if overall else "degraded",
        "version": ctx.config.server.version,
        "started_at": ctx.started_at,
        "uptime_s": int(time.time() - ctx.started_at),
        "spokes": spokes,
    }


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/admin/")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    log.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": "internal", "detail": str(exc)[:200]})


app.include_router(ollama_router)
app.include_router(openai_router)
app.include_router(admin_router)
