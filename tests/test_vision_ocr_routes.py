"""Tests fuer die neuen /v1/vision/parse und /v1/ocr Routen (Phase 3).

Strategie: wir setzen direkt einen RuntimeSpoke in den runtime_config-Store
(per Reload aus der admin-DB) und mocken httpx.AsyncClient, damit der Proxy
nicht echt rausgeht.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


def _make_config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
server:
  host: 127.0.0.1
  port: 7842
auth:
  require_app_id: true
  allow_default: true
apps:
  - id: default
    rate_limit_rpm: 60
    max_concurrent: 4
spokes: []
routes: []
metrics:
  db_path: {tmp_path / "metrics.db"}
""",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def app_with_capabilities(monkeypatch, tmp_path: Path):
    """App mit Vision- und OCR-Spoke in der Admin-DB."""
    cfg = _make_config_file(tmp_path)
    monkeypatch.setenv("LLM_ROUTER_CONFIG", str(cfg))
    monkeypatch.setenv("ADMIN_DB_URL", f"sqlite:///{tmp_path / 'admin.db'}")

    # Module muessen frisch importiert werden, damit der Snapshot leer startet.
    import importlib

    import llm_router.main as main_mod
    import llm_router.runtime_config as rc
    main_mod = importlib.reload(main_mod)
    rc = importlib.reload(rc)

    fastapi_app = main_mod.app

    # Test-Client triggert lifespan → Admin-DB ist initialisiert.
    # Wir nutzen den Client als context manager, fuegen Spokes nach Init ein,
    # und reloaden runtime_config.
    return fastapi_app


def _setup_spokes_via_admin(tmp_path: Path) -> None:
    """Legt einen Vision- und einen OCR-Spoke direkt via CRUD an, danach Reload."""
    from llm_router import runtime_config
    from llm_router.admin.crud import spokes as crud_spokes
    from llm_router.admin.db import get_session_factory
    from llm_router.admin.models import SpokeCreate

    factory = get_session_factory()
    with factory() as s:
        # Beide existieren noch nicht — sicherheitshalber name-checks.
        if not crud_spokes.get_spoke_by_name(s, "test-vision"):
            crud_spokes.create_spoke(
                s,
                SpokeCreate(
                    name="test-vision",
                    base_url="http://mock-vision.local:9100",
                    type="custom",
                    capabilities=["vision"],
                    priority=10,
                ),
            )
        if not crud_spokes.get_spoke_by_name(s, "test-ocr"):
            crud_spokes.create_spoke(
                s,
                SpokeCreate(
                    name="test-ocr",
                    base_url="http://mock-ocr.local:9101",
                    type="paddle-ocr",
                    capabilities=["ocr"],
                    priority=10,
                ),
            )
    runtime_config.reload_from_admin_db()


def _mock_httpx_success(monkeypatch, captured: dict):
    """httpx.AsyncClient mock — captured wird mit url+headers+body befuellt."""

    class MockResp:
        status_code = 200
        headers = httpx.Headers({"content-type": "application/json"})

        async def aiter_raw(self):
            yield b'{"ok": true}'

        async def aread(self):
            return b'{"ok": true}'

        async def aclose(self):
            return None

    class MockClient:
        def __init__(self, *a, **kw):
            pass

        def build_request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            captured["body"] = content
            return httpx.Request(method, url)

        async def send(self, *a, **kw):
            return MockResp()

        async def aclose(self):
            return None

    monkeypatch.setattr("llm_router.proxy.httpx.AsyncClient", MockClient)


def test_vision_parse_routes_to_vision_spoke(app_with_capabilities, monkeypatch, tmp_path):
    captured: dict = {}
    _mock_httpx_success(monkeypatch, captured)

    with TestClient(app_with_capabilities) as client:
        _setup_spokes_via_admin(tmp_path)
        r = client.post(
            "/v1/vision/parse",
            json={"image_url": "http://x/y.png"},
        )
    assert r.status_code == 200, r.text
    assert captured["url"].startswith("http://mock-vision.local:9100/v1/vision/parse")
    # Spoke-Name im Response-Header
    assert r.headers.get("X-Llm-Spoke") == "test-vision"


def test_ocr_routes_to_ocr_spoke_with_multipart(app_with_capabilities, monkeypatch, tmp_path):
    """OCR-Route mit multipart/form-data: Body unveraendert weiterreichen."""
    captured: dict = {}
    _mock_httpx_success(monkeypatch, captured)

    with TestClient(app_with_capabilities) as client:
        _setup_spokes_via_admin(tmp_path)
        # multipart file upload — FastAPI/TestClient generiert multipart-body
        r = client.post(
            "/v1/ocr",
            files={"file": ("scan.png", b"\x89PNG\x00", "image/png")},
        )
    assert r.status_code == 200, r.text
    assert captured["url"].startswith("http://mock-ocr.local:9101/v1/ocr")
    # Body muss multipart sein und das PNG-Magic enthalten — d.h. wir haben NICHT
    # versucht, das als JSON zu parsen.
    body = captured["body"]
    assert isinstance(body, (bytes, bytearray))
    assert b"\x89PNG" in body
    # Content-Type-Header sollte multipart sein
    ct_keys = [k.lower() for k in captured["headers"].keys()]
    assert "content-type" in ct_keys
    ct_value = captured["headers"][[k for k in captured["headers"] if k.lower() == "content-type"][0]]
    assert ct_value.lower().startswith("multipart/form-data")


def test_vision_returns_503_without_spoke(app_with_capabilities, monkeypatch):
    """Wenn kein Spoke mit capability=vision existiert: 503."""
    # WICHTIG: Spokes NICHT setupen — Runtime ist leer.
    with TestClient(app_with_capabilities) as client:
        # runtime_config bleibt leer fuer vision
        r = client.post("/v1/vision/parse", json={"image_url": "http://x"})
    assert r.status_code == 503
    assert "no vision spoke" in r.text.lower()


def test_ocr_returns_503_without_spoke(app_with_capabilities, monkeypatch):
    with TestClient(app_with_capabilities) as client:
        r = client.post("/v1/ocr", files={"file": ("a.png", b"x", "image/png")})
    assert r.status_code == 503
    assert "no ocr spoke" in r.text.lower()
