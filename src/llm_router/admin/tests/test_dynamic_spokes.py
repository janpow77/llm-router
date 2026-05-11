"""Dynamic-Spoke-Registration + Heartbeat-Tests (Phase 3)."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture()
def spoke_token(monkeypatch):
    monkeypatch.setenv("SPOKE_REGISTRATION_TOKEN", "shared-test-token")
    return "shared-test-token"


@pytest.fixture()
def spoke_headers(spoke_token):
    return {"X-Spoke-Token": spoke_token}


def test_register_dynamic_spoke_happy_path(client, spoke_headers):
    """POST /spokes/register legt einen neuen Spoke mit source='dynamic' an."""
    payload = {
        "name": "dyn-nuc-ocr",
        "base_url": "http://10.0.0.5:9001",
        "type": "paddle-ocr",
        "capabilities": ["ocr"],
        "tags": ["dynamic", "ocr"],
        "priority": 200,
        "version": "paddle-3.0.1",
        "source": "dynamic",
    }
    r = client.post("/admin/api/spokes/register", json=payload, headers=spoke_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "dynamic"
    assert body["status"] == "online"
    assert body["capabilities"] == ["ocr"]
    assert body["version"] == "paddle-3.0.1"
    assert body["last_seen_at"]


def test_register_dynamic_spoke_is_idempotent(client, spoke_headers):
    """Zweiter Call mit gleichem Namen → 200 (Update), kein 409."""
    payload = {
        "name": "dyn-vision",
        "base_url": "http://10.0.0.6:9002",
        "type": "custom",
        "capabilities": ["vision"],
        "source": "dynamic",
    }
    r1 = client.post("/admin/api/spokes/register", json=payload, headers=spoke_headers)
    assert r1.status_code == 201
    first_id = r1.json()["id"]
    # Erneut mit anderer base_url (Endpoint-Wechsel) → Update.
    payload["base_url"] = "http://10.0.0.7:9002"
    r2 = client.post("/admin/api/spokes/register", json=payload, headers=spoke_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == first_id
    assert body["base_url"] == "http://10.0.0.7:9002"


def test_register_without_token_returns_501_when_disabled(client, monkeypatch):
    """Ohne gesetzte Env-Variable: 501 Not Implemented."""
    monkeypatch.delenv("SPOKE_REGISTRATION_TOKEN", raising=False)
    payload = {"name": "x", "base_url": "http://x", "source": "dynamic"}
    r = client.post("/admin/api/spokes/register", json=payload)
    assert r.status_code == 501


def test_register_with_wrong_token_returns_401(client, spoke_token):
    payload = {"name": "x", "base_url": "http://x", "source": "dynamic"}
    r = client.post(
        "/admin/api/spokes/register",
        json=payload,
        headers={"X-Spoke-Token": "wrong"},
    )
    assert r.status_code == 401


def test_heartbeat_bumps_last_seen(client, spoke_headers):
    payload = {
        "name": "dyn-hb",
        "base_url": "http://10.0.0.8:9003",
        "type": "custom",
        "capabilities": ["llm"],
        "source": "dynamic",
    }
    created = client.post(
        "/admin/api/spokes/register", json=payload, headers=spoke_headers,
    ).json()
    spoke_id = created["id"]
    first_seen = created["last_seen_at"]

    # Heartbeat
    r = client.post(
        f"/admin/api/spokes/{spoke_id}/heartbeat",
        headers=spoke_headers,
    )
    assert r.status_code == 204

    # Re-fetch via list (registration response only — no need for auth here).
    # Wir lesen direkt aus der DB via CRUD um auth-Frage zu umgehen.
    from llm_router.admin.crud import spokes as crud_spokes
    from llm_router.admin.db import get_session_factory

    with get_session_factory()() as session:
        row = crud_spokes.get_spoke(session, spoke_id)
        assert row is not None
        assert row.last_seen_at is not None
        # last_seen_at sollte >= dem ersten Wert sein.
        assert row.last_seen_at >= first_seen


def test_heartbeat_unknown_spoke_returns_404(client, spoke_headers):
    r = client.post(
        "/admin/api/spokes/spk_does_not_exist/heartbeat",
        headers=spoke_headers,
    )
    assert r.status_code == 404


def test_heartbeat_sweep_marks_stale_offline(session, spoke_token):
    """Spokes ohne Heartbeat > timeout werden auf offline gesetzt."""
    from llm_router.admin.crud import spokes as crud_spokes
    from llm_router.admin.db import get_session_factory
    from llm_router.admin.models import SpokeRegister
    from llm_router.admin.services import heartbeat as hb

    payload = SpokeRegister(
        name="dyn-stale",
        base_url="http://10.0.0.9:9004",
        type="custom",
        capabilities=["llm"],
    )
    row, _ = crud_spokes.upsert_dynamic_spoke(session, payload)
    spoke_id = row.id

    # Manuell auf alten Heartbeat setzen.
    stale_ts = (datetime.now(tz=UTC) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    row.last_seen_at = stale_ts
    session.commit()

    factory = get_session_factory()
    transitioned = hb.sweep_once(factory, timeout_s=90)
    assert transitioned == 1

    # Re-lesen
    with factory() as s:
        row = crud_spokes.get_spoke(s, spoke_id)
        assert row.status == "offline"
        assert row.last_error and "heartbeat timeout" in row.last_error


def test_heartbeat_sweep_ignores_manual_spokes(session):
    """Manuelle Spokes (source='manual') werden NICHT vom Sweep angefasst."""
    from llm_router.admin.crud import spokes as crud_spokes
    from llm_router.admin.db import get_session_factory
    from llm_router.admin.models import SpokeCreate
    from llm_router.admin.services import heartbeat as hb

    payload = SpokeCreate(name="manual-spoke", base_url="http://manual.local", type="ollama")
    row = crud_spokes.create_spoke(session, payload)
    assert row.source == "manual"
    # Kein last_seen_at → Sweep darf trotzdem nicht offline schalten (manual).
    factory = get_session_factory()
    transitioned = hb.sweep_once(factory, timeout_s=1)
    assert transitioned == 0


def test_offline_dynamic_spoke_is_excluded_from_routing(session, spoke_token):
    """Nach Heartbeat-Timeout darf route_for_model() den Spoke nicht mehr liefern."""
    from llm_router import runtime_config
    from llm_router.admin.crud import spokes as crud_spokes
    from llm_router.admin.models import SpokeRegister

    payload = SpokeRegister(
        name="dyn-ocr-route",
        base_url="http://10.0.0.10:9005",
        type="paddle-ocr",
        capabilities=["ocr"],
        priority=10,
    )
    row, _ = crud_spokes.upsert_dynamic_spoke(session, payload)

    # 1. Online: Routing liefert den Spoke.
    runtime_config.reload_from_admin_db()
    chosen = runtime_config.route_for_model("", capability="ocr")
    assert chosen is not None and chosen.name == "dyn-ocr-route"

    # 2. Offline markieren + Reload.
    row.status = "offline"
    session.commit()
    runtime_config.reload_from_admin_db()

    chosen2 = runtime_config.route_for_model("", capability="ocr")
    assert chosen2 is None or chosen2.name != "dyn-ocr-route"
