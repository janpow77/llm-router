"""Pytest-Fixtures fuer das Admin-Backend.

- Eigene SQLite-Datei pro Testlauf (tmp_path)
- Admin-Passwort: "test-pw"
- FastAPI-TestClient mit eingebundenem Admin-Router
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# sys.path Bootstrap (Tests laufen ohne Editable-Install)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(autouse=True)
def _admin_password(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_ADMIN_PASSWORD", "test-pw")
    monkeypatch.setenv("ADMIN_DISABLE_HEALTH_LOOP", "1")
    yield


@pytest.fixture()
def db_url(tmp_path):
    """Pro Test eine eigene SQLite-Datei (kein In-Memory, da WAL-Pragma)."""
    path = tmp_path / "admin.db"
    return f"sqlite:///{path}"


@pytest.fixture()
def session(db_url):
    from llm_router.admin.db import reset_for_tests, get_session_factory
    reset_for_tests(db_url=db_url)
    factory = get_session_factory()
    s = factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def app(db_url):
    """FastAPI-App mit nur dem Admin-Router."""
    from llm_router.admin.db import reset_for_tests
    from llm_router.admin.router import router

    reset_for_tests(db_url=db_url)
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def auth_token(client):
    resp = client.post("/admin/api/auth/login", json={"password": "test-pw"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture()
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
