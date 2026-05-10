"""FastAPI-Dependencies und Shared Context."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

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

    Liefert die ``AppConfig``. Wirft HTTPException(401|403|429) bei Fehlern.

    Wichtig: Wenn diese Funktion erfolgreich zurückkehrt, wurde ein Slot beim
    RateLimiter belegt. Das ``release`` erfolgt im Middleware-Layer am Ende
    des Requests (siehe main.py — wir setzen request.state.app_id).
    """
    auth = ctx.config.auth
    app_id = request.headers.get("x-app-id")
    if not app_id:
        if auth.require_app_id and not auth.allow_default:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-App-Id Header fehlt",
            )
        app_id = "default"

    app = ctx.config.app_by_id(app_id)
    if app is None:
        # Unbekannte App → fallback default
        if auth.allow_default:
            app = ctx.config.app_by_id("default") or AppConfig(id="default")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unbekannte App: {app_id}",
            )

    # API-Key prüfen, wenn konfiguriert
    if auth.api_key_required and app.api_key:
        provided = request.headers.get("x-api-key")
        if provided != app.api_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ungültiger oder fehlender X-Api-Key",
            )

    # Rate-Limit
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
