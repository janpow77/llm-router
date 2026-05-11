"""Ollama-kompatible Routen.

Reicht /api/generate, /api/chat, /api/tags, /api/embeddings transparent durch.
Damit funktionieren alle Clients die heute direkt gegen Ollama sprechen
(z.B. das auditworkshop ollama_service.py) ohne Code-Änderung — nur Base-URL
auf den Router umbiegen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ._model_aggregation import aggregate_ollama_tags
from .deps import RouterContext, get_context, identify_app, route_for_model
from .proxy import proxy

router = APIRouter(tags=["ollama"])


def _model_for_request(body: bytes) -> str | None:
    from .proxy import _extract_model_from_payload

    return _extract_model_from_payload(body)


@router.api_route("/api/generate", methods=["POST"])
async def ollama_generate(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _model_for_request(body) or ""
    spoke = route_for_model(model)
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/api/generate",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/generate",
        response_kind="ollama",
    )


@router.api_route("/api/chat", methods=["POST"])
async def ollama_chat(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _model_for_request(body) or ""
    spoke = route_for_model(model)
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/api/chat",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/chat",
        response_kind="ollama",
    )


@router.api_route("/api/embeddings", methods=["POST"])
async def ollama_embeddings(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _model_for_request(body) or ""
    spoke = route_for_model(model, capability="embedding")
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/api/embeddings",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/embeddings",
        response_kind="ollama",
    )


@router.api_route("/api/embed", methods=["POST"])
async def ollama_embed(request: Request, ctx: RouterContext = Depends(get_context)):
    """Neuere Ollama-Variante (`/api/embed` mit `input`)."""
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _model_for_request(body) or ""
    spoke = route_for_model(model, capability="embedding")
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/api/embed",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/embed",
        response_kind="ollama",
    )


@router.api_route("/api/tags", methods=["GET"])
async def ollama_tags(request: Request, ctx: RouterContext = Depends(get_context)):
    """Aggregiert /api/tags ueber alle llm-capable Spokes.

    Vorher: nur Default-Spoke proxiert — Clients sahen nur einen Bruchteil der
    Modelle, was bei Workshop's `_resolve_model`-Fallback zu Mis-Routing
    fuehrte. Jetzt: alle routable llm-Spokes werden parallel abgefragt,
    Modelle nach Name dedupliziert. ``_spoke``/``_spokes`` Metadaten zeigen
    welcher Spoke das Modell bedient.
    """
    await identify_app(request, ctx)
    merged = await aggregate_ollama_tags()
    if not merged.get("models"):
        return JSONResponse(status_code=503, content={"error": "no spoke reachable"})
    return JSONResponse(content=merged, headers={"x-llm-aggregated": "true"})


@router.api_route("/api/show", methods=["POST"])
async def ollama_show(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    spoke = route_for_model(_model_for_request(body) or "")
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/api/show",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/show",
        response_kind="ollama",
    )


@router.api_route("/api/version", methods=["GET"])
async def ollama_version(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    spoke = route_for_model("")
    if not spoke:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="GET",
        spoke=spoke,
        upstream_path="/api/version",
        headers=dict(request.headers),
        body=b"",
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/api/version",
        response_kind="ollama",
    )
