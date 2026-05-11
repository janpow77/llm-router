"""FastAPI-Dependencies und Shared Context.

Wichtig: identify_app + Routing-Helpers nutzen primaer den
``runtime_config``-Store (Admin-DB als Source-of-Truth, YAML als Fallback).
Direkter Zugriff auf ``ctx.config.app_by_id``/``ctx.config.route_for_model``
sollte ueberall durch die Helpers in dieser Datei ersetzt werden.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from . import runtime_config
from .config import AppConfig, RouterConfig
from .metrics import MetricsStore
from .ratelimit import RateLimiter


@dataclass
class RouterContext:
    config: RouterConfig
    metrics: MetricsStore
    limiter: RateLimiter
    started_at: float


def get_context(request: Request) -> RouterContext:
    return request.app.state.ctx


async def identify_app(request: Request, ctx: RouterContext) -> AppConfig:
    """Liest X-App-Id, validiert ggf. X-Api-Key, prüft Rate-Limit.

    Lookup-Reihenfolge (Hybrid C):
    1. Admin-DB (via runtime_config)
    2. YAML-Fallback (ctx.config)

    Liefert die ``AppConfig``. Wirft HTTPException(401|403|429) bei Fehlern.

    Wichtig: Wenn diese Funktion erfolgreich zurückkehrt, wurde ein Slot beim
    RateLimiter belegt. Das ``release`` erfolgt im Middleware-Layer am Ende
    des Requests (siehe main.py — wir setzen request.state.app_id).
    """
    auth = ctx.config.auth
    app_id = request.headers.get("x-app-id")
    provided_key = request.headers.get("x-api-key")

    # API-Key-First: wenn ein Klartext-Key mitkommt, schauen wir DB nach Hash.
    # Wirkt vor allen X-App-Id-Pruefungen, weil der Key implizit auch die App identifiziert.
    if provided_key:
        app_via_key = runtime_config.app_by_api_key(provided_key)
        if app_via_key is not None:
            app = app_via_key
            return await _finalize_app_auth(request, ctx, app)
        if auth.api_key_required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ungültiger X-Api-Key",
            )

    if not app_id:
        if auth.require_app_id and not auth.allow_default:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-App-Id Header fehlt",
            )
        app_id = "default"

    # Admin-DB → YAML-Fallback (innerhalb von runtime_config gekapselt)
    app = runtime_config.app_by_name(app_id)
    if app is None:
        if auth.allow_default:
            app = runtime_config.app_by_name("default") or AppConfig(id="default")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unbekannte App: {app_id}",
            )

    # API-Key-Pflicht: wenn die App in YAML einen Klartext-Key hat, gegenpruefen
    # (Admin-DB-Apps wurden oben ueber app_by_api_key erschoepfend behandelt)
    if auth.api_key_required and app.api_key and provided_key != app.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ungültiger oder fehlender X-Api-Key",
        )

    return await _finalize_app_auth(request, ctx, app)


async def _finalize_app_auth(request: Request, ctx: RouterContext, app: AppConfig) -> AppConfig:
    """Rate-Limit + Request-State setzen. Gemeinsamer Endpfad fuer beide Auth-Wege."""
    allowed, retry_after = await ctx.limiter.acquire(app.id, app.rate_limit_rpm, app.max_concurrent)
    if not allowed:
        headers = {"Retry-After": str(retry_after or 1)}
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate-Limit erreicht für App {app.id}",
            headers=headers,
        )
    request.state.app_id = app.id
    request.state.app_acquired = True
    return app


def route_for_model(model: str, capability: str = "llm"):
    """Wrapper auf runtime_config.route_for_model (Admin-DB > YAML)."""
    return runtime_config.route_for_model(model, capability=capability)
