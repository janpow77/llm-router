"""Aggregiert /api/tags und /v1/models ueber alle llm-capable Spokes.

Zweck: Clients wie auditworkshop's ``_resolve_model`` fragen ``/api/tags`` ab,
um zu pruefen ob ein Modell verfuegbar ist. Bisher proxierte der Router das
nur an den Default-Spoke — Modelle anderer Spokes blieben unsichtbar, was zu
faelschlichen Fallbacks fuehrte. Hier sammeln wir parallel von allen
routablen Spokes und dedupen nach Modell-Name.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .runtime_config import RuntimeSpoke, snapshot

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 2.5


_AGGREGATABLE_CAPS = {"llm", "embedding", "vision", "ocr", "rerank"}


def _routable_llm_spokes() -> list[RuntimeSpoke]:
    """Spokes mit Modell-Listen die der Router via /api/tags + /v1/models
    aggregieren kann. Schliesst alle modell-tragenden Capabilities ein —
    vision-service (vision/ocr) wird sonst von Clients nicht entdeckt.
    """
    snap = snapshot()
    out: list[RuntimeSpoke] = []
    for spk in snap.spokes_by_name.values():
        if not spk.enabled or spk.status == "offline":
            continue
        if not (set(spk.capabilities) & _AGGREGATABLE_CAPS):
            continue
        out.append(spk)
    out.sort(key=lambda s: s.priority)
    return out


def _spoke_scheme(spk: RuntimeSpoke) -> str:
    if spk.type == "gpu-llm-manager":
        return "ollama"
    return spk.type


def _build_spoke_headers(spk: RuntimeSpoke) -> dict[str, str]:
    headers = {"User-Agent": "llm-router-aggregator/1.0"}
    if spk.auth_header and spk.auth_value:
        headers[spk.auth_header] = spk.auth_value
    return headers


async def _fetch_one(
    client: httpx.AsyncClient,
    spk: RuntimeSpoke,
    path: str,
    headers: dict[str, str],
) -> tuple[str, list[dict[str, Any]]]:
    url = f"{spk.base_url.rstrip('/')}{path}"
    try:
        resp = await client.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT_S)
        if resp.status_code >= 400:
            log.debug("aggregate %s %s -> HTTP %d", spk.name, path, resp.status_code)
            return spk.name, []
        body = resp.json()
    except (httpx.RequestError, ValueError, AttributeError, TypeError) as exc:
        log.debug("aggregate %s %s failed: %s", spk.name, path, exc)
        return spk.name, []
    if path == "/api/tags":
        models = body.get("models") if isinstance(body, dict) else None
        return spk.name, list(models or [])
    data = body.get("data") if isinstance(body, dict) else None
    return spk.name, list(data or [])


async def _gather_all(spokes: list[RuntimeSpoke], ollama_path_first: bool) -> list[tuple[str, list[dict[str, Any]]]]:
    """Sammelt parallel von allen Spokes. Schlaegt bei nicht-asynccontext httpx
    (z.B. MonkeyPatch in Tests) leise fehl und liefert leere Liste.
    """
    try:
        client_ctx = httpx.AsyncClient()
        # Manche Test-Mocks ersetzen AsyncClient durch einen Nicht-Context-Manager.
        # Wir pruefen das hier upfront, damit der naechste async with sauber bleibt.
        if not hasattr(client_ctx, "__aenter__") or not hasattr(client_ctx, "__aexit__"):
            log.debug("httpx.AsyncClient is not an async context manager (test mock?) — skipping aggregation")
            return []
    except Exception as exc:  # noqa: BLE001
        log.debug("httpx.AsyncClient instantiation failed: %s", exc)
        return []
    async with client_ctx as client:
        tasks = []
        for spk in spokes:
            scheme = _spoke_scheme(spk)
            if ollama_path_first:
                path = "/api/tags" if scheme == "ollama" else "/v1/models"
            else:
                path = "/v1/models" if scheme != "ollama" else "/api/tags"
            tasks.append(_fetch_one(client, spk, path, _build_spoke_headers(spk)))
        return await asyncio.gather(*tasks, return_exceptions=False)


async def aggregate_ollama_tags() -> dict[str, Any]:
    """Sammelt /api/tags von allen llm-Spokes parallel und mergt sie."""
    spokes = _routable_llm_spokes()
    if not spokes:
        return {"models": []}
    results = await _gather_all(spokes, ollama_path_first=True)
    merged: dict[str, dict[str, Any]] = {}
    for spoke_name, items in results:
        for m in items:
            if not isinstance(m, dict):
                continue
            name = m.get("name") or m.get("id") or ""
            if not name:
                continue
            existing = merged.get(name)
            entry = dict(m)
            entry.setdefault("name", name)
            entry["_spoke"] = spoke_name
            if existing is None:
                merged[name] = entry
            else:
                existing.setdefault("_spokes", [existing.get("_spoke")])
                existing["_spokes"].append(spoke_name)
    return {"models": sorted(merged.values(), key=lambda m: m.get("name", ""))}


async def aggregate_openai_models() -> dict[str, Any]:
    """Sammelt /v1/models von allen Spokes (alias /api/tags wenn ollama-Spoke)."""
    spokes = _routable_llm_spokes()
    if not spokes:
        return {"object": "list", "data": []}
    results = await _gather_all(spokes, ollama_path_first=False)
    merged: dict[str, dict[str, Any]] = {}
    for spoke_name, items in results:
        for m in items:
            if not isinstance(m, dict):
                continue
            name = m.get("id") or m.get("name") or ""
            if not name:
                continue
            existing = merged.get(name)
            entry = {"id": name, "object": "model", "owned_by": spoke_name}
            if existing is None:
                merged[name] = entry
            else:
                existing.setdefault("_spokes", [existing.get("owned_by")])
                existing["_spokes"].append(spoke_name)
    return {"object": "list", "data": sorted(merged.values(), key=lambda m: m.get("id", ""))}
