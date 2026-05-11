"""OpenAI-kompatible Routen.

Reicht /v1/chat/completions, /v1/completions, /v1/embeddings, /v1/models
weiter — viele Bibliotheken (LangChain, OpenAI-SDK, LiteLLM) erwarten
dieses Schema. Ollama unterstützt /v1/* nativ seit 0.1.30+.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ._model_aggregation import aggregate_openai_models
from .deps import RouterContext, get_context, identify_app, route_for_model
from .proxy import _extract_model_from_payload, proxy

router = APIRouter(tags=["openai"])


@router.api_route("/v1/chat/completions", methods=["POST"])
async def openai_chat(request: Request, ctx: RouterContext = Depends(get_context)):
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _extract_model_from_payload(body) or ""
    spoke = route_for_model(model)
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
    spoke = route_for_model(model)
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
    spoke = route_for_model(model, capability="embedding")
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


@router.api_route("/v1/rerank", methods=["POST"])
async def openai_rerank(request: Request, ctx: RouterContext = Depends(get_context)):
    """Cross-Encoder-Reranking via reranker-service Spokes.

    Erwartet Payload:
      {"model": "<id>", "query": "...", "passages": ["..."], "top_k": ?, "return_documents": ?}
    Antwort: ``{model, duration_ms, scores, ranking}``. Modell-Routing identisch
    zu Embeddings — Spoke muss capability=``rerank`` haben.
    """
    app = await identify_app(request, ctx)
    body = await request.body()
    model = _extract_model_from_payload(body) or ""
    spoke = route_for_model(model, capability="rerank")
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no rerank spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/rerank",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/rerank",
        response_kind="openai",
    )


@router.api_route("/v1/vision/parse", methods=["POST"])
async def openai_vision_parse(request: Request, ctx: RouterContext = Depends(get_context)):
    """Vision/Doc-Parsing via Spokes mit capability='vision' (LLaVA/Qwen-VL/...).

    Reicht den Body unveraendert weiter — JSON oder multipart/form-data.
    Bei multipart wird der Body als bytes durchgereicht (kein json-Parse),
    der Content-Type-Header bleibt erhalten.
    """
    app = await identify_app(request, ctx)
    content_type = (request.headers.get("content-type") or "").lower()
    body = await request.body()
    model = ""
    # Modell nur aus JSON-Body extrahieren — bei multipart bleibt es leer und
    # das Routing greift auf den ersten Spoke mit capability=vision zurueck.
    if "application/json" in content_type:
        model = _extract_model_from_payload(body) or ""
    spoke = route_for_model(model, capability="vision")
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no vision spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/vision/parse",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/vision/parse",
        response_kind="openai",
    )


@router.api_route("/v1/ocr", methods=["POST"])
async def openai_ocr(request: Request, ctx: RouterContext = Depends(get_context)):
    """OCR via Spokes mit capability='ocr' (PaddleOCR, RapidOCR, ...).

    Reicht den Body unveraendert weiter — typischerweise multipart/form-data
    mit einer Bild-/PDF-Datei. JSON-Bodies (mit base64-Payload) werden
    ebenfalls akzeptiert.
    """
    app = await identify_app(request, ctx)
    content_type = (request.headers.get("content-type") or "").lower()
    body = await request.body()
    model = ""
    if "application/json" in content_type:
        model = _extract_model_from_payload(body) or ""
    spoke = route_for_model(model, capability="ocr")
    if not spoke:
        return JSONResponse(status_code=503, content={"error": "no ocr spoke configured"})
    return await proxy(
        method="POST",
        spoke=spoke,
        upstream_path="/v1/ocr",
        headers=dict(request.headers),
        body=body,
        query=str(request.url.query or ""),
        app_id=app.id,
        metrics=ctx.metrics,
        route_label="/v1/ocr",
        response_kind="openai",
    )


@router.api_route("/v1/models", methods=["GET"])
async def openai_models(request: Request, ctx: RouterContext = Depends(get_context)):
    """Aggregiert /v1/models ueber alle Spokes (ollama-Spokes via /api/tags)."""
    await identify_app(request, ctx)
    merged = await aggregate_openai_models()
    if not merged.get("data"):
        return JSONResponse(status_code=503, content={"error": "no spoke reachable"})
    return JSONResponse(content=merged, headers={"x-llm-aggregated": "true"})
