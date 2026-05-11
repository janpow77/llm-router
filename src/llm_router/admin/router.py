"""APIRouter fuer ``/admin/api/*``.

Bindet alle Endpoints gemaess ``frontend/api-contract.md``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from .auth import (
    cleanup_expired,
    client_ip,
    issue_token,
    lookup_session,
    require_auth,
    revoke_token,
    verify_password,
)
from .crud import apps as crud_apps
from .crud import audit as crud_audit
from .crud import quotas as crud_quotas
from .crud import routes as crud_routes
from .crud import settings as crud_settings
from .crud import spokes as crud_spokes
from .db import get_session
from .models import (
    AppCreate,
    AppCreateResponse,
    AppOut,
    AppUpdate,
    AuditOut,
    LoginRequest,
    LoginResponse,
    MeResponse,
    ModelOut,
    QuotaOut,
    QuotaUpdate,
    RouteCreate,
    RouteOut,
    RouteUpdate,
    SettingsOut,
    SettingsUpdate,
    SpokeCreate,
    SpokeOut,
    SpokeUpdate,
    app_row_to_out,
    audit_row_to_out,
    model_row_to_out,
    route_row_to_out,
    spoke_row_to_out,
)
from .services import log_stream, model_discovery, spoke_health

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api", tags=["admin-api"])


# ----------------------------- Health (open) -------------------------------


@router.get("/health")
async def health(session: Session = Depends(get_session)) -> dict:
    from .models import SpokeRow

    spokes = session.query(SpokeRow).all()
    started = _started_at_iso()
    return {
        "status": "ok",
        "version": _router_version(),
        "started_at": started,
        "spokes_health": [
            {
                "spoke_id": s.id,
                "name": s.name,
                "status": s.status,
                "last_check_at": s.last_check_at,
            }
            for s in spokes
        ],
    }


# ----------------------------- Auth (open + protected) ---------------------


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, session: Session = Depends(get_session)) -> LoginResponse:
    if not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    cleanup_expired(session)
    token, expires = issue_token(session, ip=client_ip(request))
    return LoginResponse(token=token, expires_at=expires)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, _=Depends(require_auth), session: Session = Depends(get_session)) -> Response:
    auth_header = request.headers.get("authorization") or ""
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif token_q := request.query_params.get("token"):
        token = token_q
    if token:
        revoke_token(session, token)
    return Response(status_code=204)


@router.get("/auth/me", response_model=MeResponse)
async def auth_me(session_row=Depends(require_auth)) -> MeResponse:
    from .auth import _from_iso

    try:
        expires = _from_iso(session_row.expires_at)
    except ValueError:
        expires = None
    return MeResponse(logged_in=True, expires_at=expires)


# ----------------------------- Dashboard -----------------------------------


@router.get("/dashboard")
async def dashboard(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    from .models import AppRow, SpokeRow

    agg = log_stream.aggregate_dashboard(hours=24)
    active_spokes = session.query(SpokeRow).filter(SpokeRow.status == "online").count()
    active_apps = session.query(AppRow).filter(AppRow.enabled == 1).count()
    agg["active_spokes"] = active_spokes
    agg["active_apps"] = active_apps
    return agg


@router.get("/dashboard/timeseries")
async def dashboard_timeseries(
    _=Depends(require_auth),
    bucket: str = Query("1h", pattern="^(5m|15m|1h)$"),
    hours: int = Query(24, ge=1, le=168),
) -> list[dict]:
    return log_stream.aggregate_timeseries(bucket=bucket, hours=hours)


# ----------------------------- Apps CRUD -----------------------------------


def _app_count_index() -> dict[str, int]:
    return log_stream.app_request_counts_today()


@router.get("/apps", response_model=list[AppOut])
async def apps_list(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[AppOut]:
    counts = _app_count_index()
    rows = crud_apps.list_apps(session)
    return [app_row_to_out(r, request_count_today=counts.get(r.name, 0)) for r in rows]


@router.post("/apps", response_model=AppCreateResponse, status_code=201)
async def apps_create(
    payload: AppCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppCreateResponse:
    try:
        row, plain_key = crud_apps.create_app(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    out = app_row_to_out(row)
    return AppCreateResponse(**out.model_dump(), api_key=plain_key)


@router.get("/apps/{app_id}")
async def apps_get(app_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    row = crud_apps.get_app(session, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    counts = _app_count_index()
    base = app_row_to_out(row, request_count_today=counts.get(row.name, 0)).model_dump(mode="json")
    base["recent_requests"] = log_stream.app_recent_requests(row.name, limit=50)
    return base


@router.patch("/apps/{app_id}", response_model=AppOut)
async def apps_patch(
    app_id: str,
    patch: AppUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppOut:
    try:
        row = crud_apps.update_app(session, app_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app_row_to_out(row)


@router.delete("/apps/{app_id}", status_code=204)
async def apps_delete(
    app_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_apps.delete_app(session, app_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="App not found")
    return Response(status_code=204)


@router.post("/apps/{app_id}/rotate-key")
async def apps_rotate(
    app_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    result = crud_apps.rotate_key(session, app_id, ip=client_ip(request))
    if result is None:
        raise HTTPException(status_code=404, detail="App not found")
    _, plain = result
    return {"api_key": plain}


@router.post("/apps/{app_id}/toggle-enabled", response_model=AppOut)
async def apps_toggle(
    app_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppOut:
    row = crud_apps.toggle_enabled(session, app_id, ip=client_ip(request))
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app_row_to_out(row)


# ----------------------------- Spokes CRUD ---------------------------------


@router.get("/spokes", response_model=list[SpokeOut])
async def spokes_list(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[SpokeOut]:
    rows = crud_spokes.list_spokes(session)
    return [spoke_row_to_out(r, models=crud_spokes.list_models_for_spoke(session, r.id)) for r in rows]


@router.post("/spokes", response_model=SpokeOut, status_code=201)
async def spokes_create(
    payload: SpokeCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SpokeOut:
    try:
        row = crud_spokes.create_spoke(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Best-effort initialer Discover (nicht blockierend bei Fehlern)
    try:
        await model_discovery.discover_for_spoke(session, row)
    except Exception as exc:
        log.info("Initial-Discovery fuer %s schlug fehl: %s", row.name, exc)
    session.refresh(row)
    return spoke_row_to_out(row, models=crud_spokes.list_models_for_spoke(session, row.id))


@router.get("/spokes/{spoke_id}", response_model=SpokeOut)
async def spokes_get(spoke_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> SpokeOut:
    row = crud_spokes.get_spoke(session, spoke_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Spoke not found")
    return spoke_row_to_out(row, models=crud_spokes.list_models_for_spoke(session, spoke_id))


@router.patch("/spokes/{spoke_id}", response_model=SpokeOut)
async def spokes_patch(
    spoke_id: str,
    patch: SpokeUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SpokeOut:
    try:
        row = crud_spokes.update_spoke(session, spoke_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Spoke not found")
    return spoke_row_to_out(row, models=crud_spokes.list_models_for_spoke(session, spoke_id))


@router.delete("/spokes/{spoke_id}", status_code=204)
async def spokes_delete(
    spoke_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_spokes.delete_spoke(session, spoke_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Spoke not found")
    return Response(status_code=204)


@router.post("/spokes/{spoke_id}/health-check", response_model=SpokeOut)
async def spokes_health_check(
    spoke_id: str,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SpokeOut:
    row = crud_spokes.get_spoke(session, spoke_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Spoke not found")
    # Im running event loop koennen wir asyncio.run nicht nutzen — nutze die Coroutine direkt.
    from .services.spoke_health import _iso_now, _ping_spoke

    status_, error, models_payload = await _ping_spoke(row)
    row.status = status_
    row.last_check_at = _iso_now()
    row.last_error = error
    row.updated_at = _iso_now()
    if models_payload:
        model_discovery.persist_models(session, row, models_payload, commit=False)
    session.commit()
    session.refresh(row)
    return spoke_row_to_out(row, models=crud_spokes.list_models_for_spoke(session, spoke_id))


# ----------------------------- Models --------------------------------------


@router.get("/models", response_model=list[ModelOut])
async def models_list(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[ModelOut]:
    from .models import ModelRow

    rows = session.query(ModelRow).order_by(ModelRow.name.asc()).all()
    return [model_row_to_out(r) for r in rows]


@router.post("/models/refresh")
async def models_refresh(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    discovered = await model_discovery.discover_all(session)
    return {"discovered": discovered, "updated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")}


# ----------------------------- Routes (Routing-Regeln) ---------------------


@router.get("/routes", response_model=list[RouteOut])
async def routes_list(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[RouteOut]:
    return [route_row_to_out(r, name) for r, name in crud_routes.list_routes(session)]


@router.post("/routes", response_model=RouteOut, status_code=201)
async def routes_create(
    payload: RouteCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> RouteOut:
    try:
        row = crud_routes.create_route(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return route_row_to_out(row, crud_routes.get_spoke_name(session, row.spoke_id))


@router.patch("/routes/{route_id}", response_model=RouteOut)
async def routes_patch(
    route_id: str,
    patch: RouteUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> RouteOut:
    try:
        row = crud_routes.update_route(session, route_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route_row_to_out(row, crud_routes.get_spoke_name(session, row.spoke_id))


@router.delete("/routes/{route_id}", status_code=204)
async def routes_delete(
    route_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_routes.delete_route(session, route_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Route not found")
    return Response(status_code=204)


# ----------------------------- Quotas --------------------------------------


@router.get("/quotas/{app_id}", response_model=QuotaOut)
async def quotas_get(app_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> QuotaOut:
    out = crud_quotas.get_quota(session, app_id)
    if out is None:
        raise HTTPException(status_code=404, detail="App not found")
    return out


@router.patch("/quotas/{app_id}", response_model=QuotaOut)
async def quotas_patch(
    app_id: str,
    patch: QuotaUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> QuotaOut:
    out = crud_quotas.update_quota(session, app_id, patch, ip=client_ip(request))
    if out is None:
        raise HTTPException(status_code=404, detail="App not found")
    return out


# ----------------------------- Logs ----------------------------------------


@router.get("/logs")
async def logs_recent(
    _=Depends(require_auth),
    app_id: str | None = None,
    model: str | None = None,
    status: str | None = Query(default=None, pattern="^(ok|error)$"),
    limit: int = Query(100, ge=1, le=1000),
    since: str | None = None,
) -> list[dict]:
    return log_stream.read_recent(
        app_id=app_id, model=model, status=status, since=since, limit=limit,
    )


@router.get("/logs/stream")
async def logs_stream(_=Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(
        log_stream.stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ----------------------------- Audit ---------------------------------------


@router.get("/audit", response_model=list[AuditOut])
async def audit_list(
    _=Depends(require_auth),
    actor: str | None = None,
    action: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    rows = crud_audit.list_audit(session, actor=actor, action=action, target=target, since=since, limit=limit)
    return [audit_row_to_out(r) for r in rows]


# ----------------------------- Settings ------------------------------------


@router.get("/settings", response_model=SettingsOut)
async def settings_get(_=Depends(require_auth), session: Session = Depends(get_session)) -> SettingsOut:
    return _build_settings(session)


@router.patch("/settings", response_model=SettingsOut)
async def settings_patch(
    patch: SettingsUpdate,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SettingsOut:
    payload: dict[str, Any] = {}
    if patch.log_retention_days is not None:
        payload["log_retention_days"] = patch.log_retention_days
    if patch.default_quotas is not None:
        payload["default_quotas"] = patch.default_quotas.model_dump()
    if patch.spoke_health_interval_s is not None:
        payload["spoke_health_interval_s"] = patch.spoke_health_interval_s
    if payload:
        crud_settings.update_partial(session, payload)
    return _build_settings(session)


# ----------------------------- Helpers -------------------------------------


def _started_at_iso() -> str:
    """Liefert den App-Startzeitpunkt aus ``router.state`` falls vorhanden."""
    started = _ADMIN_STATE.get("started_at")
    if started is None:
        started = time.time()
        _ADMIN_STATE["started_at"] = started
    return datetime.fromtimestamp(started, tz=UTC).isoformat().replace("+00:00", "Z")


def _router_version() -> str:
    try:
        from .. import __version__
        return __version__
    except Exception:
        return os.environ.get("LLM_ROUTER_VERSION", "0.1.0")


def _build_settings(session: Session) -> SettingsOut:
    from .models import QuotaConfig

    raw = crud_settings.get_all(session)
    defaults_dict = raw.get("default_quotas") or {}
    if isinstance(defaults_dict, dict):
        defaults = QuotaConfig(**{k: v for k, v in defaults_dict.items() if k in {"rpm", "concurrent", "daily_tokens"}})
    else:
        defaults = QuotaConfig()
    started = _ADMIN_STATE.get("started_at") or time.time()
    uptime = int(time.time() - started)
    return SettingsOut(
        router_version=_router_version(),
        uptime_seconds=uptime,
        log_retention_days=int(raw.get("log_retention_days") or 30),
        default_quotas=defaults,
        data_dir=os.environ.get("ADMIN_DATA_DIR", "/data"),
        config_path=os.environ.get("LLM_ROUTER_CONFIG", "/etc/llm-router/config.yaml"),
        spoke_health_interval_s=int(raw.get("spoke_health_interval_s") or 30),
    )


# Modul-level State, das vom Lifespan gesetzt wird (Startzeit, Stop-Event).
# Wird von ``startup_admin``/``shutdown_admin`` gepflegt.
_ADMIN_STATE: dict[str, Any] = {}


async def startup_admin(*, start_health_loop: bool = True, router_config=None) -> None:
    """Vom App-Lifespan zu rufen: initialisiert DB, bootstrappt Defaults,
    startet Background-Tasks.

    Parameter ``router_config``: optionales ``RouterConfig`` aus dem Router-Core.
    Wenn gesetzt, werden YAML-Spokes beim ersten Start in die admin-DB
    importiert (idempotent).
    """
    from .db import get_session_factory, init_db
    from .services.bootstrap import bootstrap_spokes

    init_db()
    _ADMIN_STATE["started_at"] = time.time()
    _ADMIN_STATE["stop_event"] = asyncio.Event()

    # Bootstrap: Default-Spokes (NUC-Ollama + NUC-egpu-managerd) + YAML-Spokes
    try:
        with get_session_factory()() as session:
            created = bootstrap_spokes(session, router_config=router_config)
            if created > 0:
                log.info("Bootstrap: %d Default-Spoke(s) angelegt.", created)
    except Exception as exc:  # noqa: BLE001
        log.warning("Bootstrap-Spokes fehlgeschlagen (nicht kritisch): %s", exc)

    if start_health_loop and not os.environ.get("ADMIN_DISABLE_HEALTH_LOOP"):
        with get_session_factory()() as session:
            interval = int(crud_settings.get_value(session, "spoke_health_interval_s") or 30)
        task = asyncio.create_task(spoke_health.health_loop(_ADMIN_STATE["stop_event"], interval_s=interval))
        _ADMIN_STATE["health_task"] = task


async def shutdown_admin() -> None:
    """Stoppt Background-Tasks. Wird vom App-Lifespan aufgerufen."""
    stop_event: asyncio.Event | None = _ADMIN_STATE.get("stop_event")
    task: asyncio.Task | None = _ADMIN_STATE.get("health_task")
    if stop_event:
        stop_event.set()
    if task:
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        except Exception as exc:
            log.warning("Spoke-Health-Task Shutdown: %s", exc)
