"""FastAPI-App für llm-router.

Routing-Hub: empfängt Ollama- und OpenAI-kompatible Requests, identifiziert
die Quell-App über X-App-Id, prüft Rate-Limits und proxt an einen GPU-Spoke.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, runtime_config
from .admin import admin_api_router
from .admin.router import shutdown_admin, startup_admin
from .config import load_config
from .deps import RouterContext
from .metrics import MetricsStore
from .proxy import spoke_health
from .ratelimit import RateLimiter
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
    # YAML als Fallback in den runtime_config-Store einhaengen.
    runtime_config.set_yaml_fallback(config)
    # Bootstrap: YAML-Spokes + GPU-Defaults werden in admin-DB importiert.
    await startup_admin(router_config=config)
    # Runtime-Snapshot aus der admin-DB neu laden — danach ist Hybrid C aktiv:
    # admin-DB ist authoritative, YAML ist Fallback.
    runtime_config.reload_from_admin_db()
    try:
        yield
    finally:
        await shutdown_admin()
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


@app.middleware("http")
async def runtime_config_reload_after_admin_mutation(request: Request, call_next):
    """Invalidiert den Runtime-Config-Snapshot nach jeder erfolgreichen Mutation.

    Greift NUR fuer ``/admin/api/*`` mit Methode POST/PATCH/PUT/DELETE und
    Status 2xx. So wird nach jedem Apps/Spokes/Routes/Quotas/Settings-Change
    der naechste Live-Request bereits den neuen Stand sehen.
    """
    response = await call_next(request)
    try:
        path = request.url.path or ""
        if (
            path.startswith("/admin/api/")
            and request.method in ("POST", "PATCH", "PUT", "DELETE")
            and 200 <= response.status_code < 300
            # Auth-Login/Logout aendern keinen Routing-State — auslassen
            and not path.startswith("/admin/api/auth/")
        ):
            runtime_config.reload_from_admin_db()
    except Exception as exc:  # noqa: BLE001
        log.warning("Runtime-Config-Reload nach Admin-Mutation fehlgeschlagen: %s", exc)
    return response


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
app.include_router(admin_api_router)


# Vollwertige Admin-SPA (Vue 3 Build) unter /admin/
# WICHTIG: Reihenfolge — admin_api_router (oben) MUSS vor dem Catch-All
# definiert sein, damit /admin/api/* nicht in den SPA-Fallback faellt.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend_dist"
if (_FRONTEND_DIR / "index.html").exists():
    if (_FRONTEND_DIR / "assets").exists():
        app.mount(
            "/admin/assets",
            StaticFiles(directory=_FRONTEND_DIR / "assets"),
            name="admin-assets",
        )

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    async def _admin_root():
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def _admin_spa(full_path: str):
        # Konkrete Datei (favicon.ico, vite.svg etc.) ausliefern, sonst SPA-Fallback
        candidate = _FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIR / "index.html")
else:
    log.warning("Admin-Frontend nicht gefunden unter %s — UI nicht verfuegbar", _FRONTEND_DIR)
