"""OpenAI-kompatible Routen.

Reicht /v1/chat/completions, /v1/completions, /v1/embeddings, /v1/models
weiter — viele Bibliotheken (LangChain, OpenAI-SDK, LiteLLM) erwarten
dieses Schema. Ollama unterstützt /v1/* nativ seit 0.1.30+.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .deps import RouterContext, get_context, identify_app
from .proxy import _extract_model_from_payload, proxy

router = APIRouter(tags=["openai"])


@router.api_route("/v1/chat/completions", methods=["POST"])
async def openai_chat(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _extract_model_from_payload(body) or ""
    spoke = ctx.config.route_for_model(model)
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/chat/completions",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/chat/completions",
        response_kind="openai",
    )


@router.api_route("/v1/completions", methods=["POST"])
async def openai_completions(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _extract_model_from_payload(body) or ""
    spoke = ctx.config.route_for_model(model)
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/completions",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/completions",
        response_kind="openai",
    )


@router.api_route("/v1/embeddings", methods=["POST"])
async def openai_embeddings(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _extract_model_from_payload(body) or ""
    spoke = ctx.config.route_for_model(model)
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/embeddings",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/embeddings",
        response_kind="openai",
    )


@router.api_route("/v1/models", methods=["GET"])
async def openai_models(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    spoke = ctx.config.route_for_model("")
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no spoke configured"})
    return await proxy(
        method="GET",
        spoke=spoke,
        upstream_path="/v1/models",
        headers=dict(request.headers),
        body=b"",
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/models",
        response_kind="openai",
    )
