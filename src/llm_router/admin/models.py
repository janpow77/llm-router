"""ORM-Modelle (SQLAlchemy 2.0, declarative_base) und Pydantic-Schemas.

ORM-Modelle bilden die Tabellen aus ``migrations/001_initial.sql`` ab.
Pydantic-Schemas werden in der Router-Schicht fuer Request/Response benutzt.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import REAL, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ----------------------------- ORM-Modelle ---------------------------------


class AppRow(Base):
    __tablename__ = "admin_apps"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=False, default="")
    api_key_hash = Column(String, nullable=False)
    api_key_preview = Column(String, nullable=False)
    allowed_models = Column(Text, nullable=False, default="[]")  # JSON-Liste
    quota_rpm = Column(Integer, nullable=False, default=60)
    quota_concurrent = Column(Integer, nullable=False, default=4)
    quota_daily_tokens = Column(Integer, nullable=False, default=1_000_000)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class SpokeRow(Base):
    __tablename__ = "admin_spokes"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    base_url = Column(String, nullable=False)
    type = Column(String, nullable=False, default="ollama")
    # Workload-Capabilities (JSON-Array: llm, embedding, ocr, compute, ...).
    capabilities = Column(Text, nullable=True)
    # Frei wählbare Tags (JSON-Array, z.B. ["gpu","nuc","rtx5070ti"]).
    tags = Column(Text, nullable=True)
    # Discovery-Snapshot ({device, vram_total_mb, vram_used_mb, util_pct}).
    gpu_info = Column(Text, nullable=True)
    # Routing-Priorität: niedriger = bevorzugt.
    priority = Column(Integer, nullable=False, default=100)
    auth_header = Column(String, nullable=True)
    auth_value = Column(String, nullable=True)
    status = Column(String, nullable=False, default="unknown")
    last_check_at = Column(String, nullable=True)
    last_error = Column(String, nullable=True)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class ModelRow(Base):
    __tablename__ = "admin_models"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    spoke_id = Column(String, ForeignKey("admin_spokes.id", ondelete="CASCADE"), nullable=False)
    spoke_name = Column(String, nullable=False)
    size_gb = Column(REAL, nullable=True)
    context_length = Column(Integer, nullable=True)
    quantization = Column(String, nullable=True)
    discovered_at = Column(String, nullable=False)


class RouteRow(Base):
    __tablename__ = "admin_routes"

    id = Column(String, primary_key=True)
    model_glob = Column(String, nullable=False)
    spoke_id = Column(String, ForeignKey("admin_spokes.id", ondelete="CASCADE"), nullable=False)
    priority = Column(Integer, nullable=False, default=100)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class QuotaRow(Base):
    __tablename__ = "admin_quotas"

    app_id = Column(String, ForeignKey("admin_apps.id", ondelete="CASCADE"), primary_key=True)
    rpm = Column(Integer, nullable=False)
    concurrent = Column(Integer, nullable=False)
    daily_tokens = Column(Integer, nullable=False)
    current_rpm = Column(Integer, nullable=False, default=0)
    current_concurrent = Column(Integer, nullable=False, default=0)
    current_daily_tokens = Column(Integer, nullable=False, default=0)
    counter_window_start = Column(String, nullable=True)
    updated_at = Column(String, nullable=False)


class AuditRow(Base):
    __tablename__ = "admin_audit"

    id = Column(String, primary_key=True)
    ts = Column(String, nullable=False)
    actor = Column(String, nullable=False, default="admin")
    action = Column(String, nullable=False)
    target = Column(String, nullable=True)
    before = Column(Text, nullable=True)
    after = Column(Text, nullable=True)
    ip = Column(String, nullable=True)


class SettingRow(Base):
    __tablename__ = "admin_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class SessionRow(Base):
    __tablename__ = "admin_sessions"

    token = Column(String, primary_key=True)
    actor = Column(String, nullable=False, default="admin")
    created_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    last_seen_at = Column(String, nullable=False)
    ip = Column(String, nullable=True)


# ----------------------------- Pydantic-Schemas ----------------------------


class QuotaConfig(BaseModel):
    rpm: int = Field(default=60, ge=1, le=100_000)
    concurrent: int = Field(default=4, ge=1, le=10_000)
    daily_tokens: int = Field(default=1_000_000, ge=0)


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    allowed_models: list[str] = Field(default_factory=list)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class AppUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    allowed_models: list[str] | None = None
    quota: QuotaConfig | None = None
    enabled: bool | None = None


class AppOut(BaseModel):
    id: str
    name: str
    description: str
    api_key_preview: str
    allowed_models: list[str]
    quota: QuotaConfig
    enabled: bool
    request_count_today: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppCreateResponse(AppOut):
    """Wird einmalig nach Erstellung zurueckgegeben — enthaelt den Klartext-API-Key."""

    api_key: str


class SpokeAuth(BaseModel):
    header: str = "Authorization"
    value: str


# Bekannte Spoke-Typen.
#   - "ollama":          direkter Ollama-Server (z.B. http://host:11434)
#   - "openai":          OpenAI-kompatibler Server (eigener oder vLLM/llama.cpp)
#   - "gpu-llm-manager": zentraler GPU-/LLM-Lifecycle-Manager (vormals
#                        "egpu-manager"). Verwaltet Modell-Swap, Lease,
#                        Multi-GPU auf NUC/evo/Desktop.
#   - "paddle-ocr":      OCR-Workload (Paddle / RapidOCR / etc.)
#   - "custom":          beliebiger HTTP-Workload, Capabilities frei waehlbar
SpokeKind = Literal["ollama", "openai", "gpu-llm-manager", "paddle-ocr", "custom"]
# Capabilities: ein Spoke kann mehrere Workload-Typen gleichzeitig anbieten.
SpokeCapability = Literal["llm", "embedding", "rerank", "ocr", "compute", "image-gen"]


class GpuInfo(BaseModel):
    device: str | None = None
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    util_pct: float | None = None


class SpokeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1)
    type: SpokeKind = "ollama"
    capabilities: list[SpokeCapability] = Field(default_factory=lambda: ["llm"])
    tags: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=10_000)
    auth: SpokeAuth | None = None
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def _strip_url(cls, v: str) -> str:
        return v.rstrip("/")


class SpokeUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    type: SpokeKind | None = None
    capabilities: list[SpokeCapability] | None = None
    tags: list[str] | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    auth: SpokeAuth | None = None
    enabled: bool | None = None


class SpokeOut(BaseModel):
    id: str
    name: str
    base_url: str
    type: str
    capabilities: list[str] = Field(default_factory=lambda: ["llm"])
    tags: list[str] = Field(default_factory=list)
    priority: int = 100
    gpu_info: GpuInfo | None = None
    status: str
    last_check_at: datetime | None = None
    last_error: str | None = None
    enabled: bool
    models: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelOut(BaseModel):
    id: str
    name: str
    spoke_id: str
    spoke_name: str
    size_gb: float | None = None
    context_length: int | None = None
    quantization: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RouteCreate(BaseModel):
    model_glob: str = Field(min_length=1)
    spoke_id: str = Field(min_length=1)
    priority: int = Field(default=100, ge=0, le=10_000)
    enabled: bool = True


class RouteUpdate(BaseModel):
    model_glob: str | None = None
    spoke_id: str | None = None
    priority: int | None = None
    enabled: bool | None = None


class RouteOut(BaseModel):
    id: str
    model_glob: str
    spoke_id: str
    spoke_name: str
    priority: int
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class QuotaUpdate(BaseModel):
    rpm: int | None = Field(default=None, ge=1)
    concurrent: int | None = Field(default=None, ge=1)
    daily_tokens: int | None = Field(default=None, ge=0)


class QuotaOut(BaseModel):
    app_id: str
    limits: QuotaConfig
    current: dict[str, int]


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime


class MeResponse(BaseModel):
    logged_in: bool
    expires_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    started_at: datetime
    spokes_health: list[dict[str, Any]] = Field(default_factory=list)


class AuditOut(BaseModel):
    id: str
    ts: datetime
    actor: str
    action: str
    target: str | None = None
    before: dict | list | None = None
    after: dict | list | None = None
    ip: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SettingsOut(BaseModel):
    router_version: str
    uptime_seconds: int
    log_retention_days: int
    default_quotas: QuotaConfig
    data_dir: str
    config_path: str
    spoke_health_interval_s: int = 30


class SettingsUpdate(BaseModel):
    log_retention_days: int | None = Field(default=None, ge=1, le=3650)
    default_quotas: QuotaConfig | None = None
    spoke_health_interval_s: int | None = Field(default=None, ge=5, le=3600)


# ----------------------------- Konvertierungs-Helfer -----------------------


def app_row_to_out(row: AppRow, request_count_today: int = 0) -> AppOut:
    """Wandelt einen ORM-Row in das API-DTO."""
    try:
        allowed = json.loads(row.allowed_models or "[]")
    except json.JSONDecodeError:
        allowed = []
    return AppOut(
        id=row.id,
        name=row.name,
        description=row.description or "",
        api_key_preview=row.api_key_preview,
        allowed_models=allowed,
        quota=QuotaConfig(
            rpm=row.quota_rpm,
            concurrent=row.quota_concurrent,
            daily_tokens=row.quota_daily_tokens,
        ),
        enabled=bool(row.enabled),
        request_count_today=request_count_today,
        created_at=_parse_dt(row.created_at),
        updated_at=_parse_dt(row.updated_at),
    )


def _decode_json_list(raw: str | None, default: list) -> list:
    if not raw:
        return list(default)
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else list(default)
    except (TypeError, ValueError):
        return list(default)


def _decode_gpu_info(raw: str | None) -> GpuInfo | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return GpuInfo(**data)
    except (TypeError, ValueError):
        return None
    return None


def spoke_row_to_out(row: SpokeRow, models: list[str] | None = None) -> SpokeOut:
    return SpokeOut(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        type=row.type,
        capabilities=_decode_json_list(row.capabilities, ["llm"]),
        tags=_decode_json_list(row.tags, []),
        priority=row.priority or 100,
        gpu_info=_decode_gpu_info(row.gpu_info),
        status=row.status,
        last_check_at=_parse_dt(row.last_check_at) if row.last_check_at else None,
        last_error=row.last_error,
        enabled=bool(row.enabled),
        models=models or [],
        created_at=_parse_dt(row.created_at),
        updated_at=_parse_dt(row.updated_at),
    )


def route_row_to_out(row: RouteRow, spoke_name: str) -> RouteOut:
    return RouteOut(
        id=row.id,
        model_glob=row.model_glob,
        spoke_id=row.spoke_id,
        spoke_name=spoke_name,
        priority=row.priority,
        enabled=bool(row.enabled),
    )


def model_row_to_out(row: ModelRow) -> ModelOut:
    return ModelOut(
        id=row.id,
        name=row.name,
        spoke_id=row.spoke_id,
        spoke_name=row.spoke_name,
        size_gb=row.size_gb,
        context_length=row.context_length,
        quantization=row.quantization,
    )


def audit_row_to_out(row: AuditRow) -> AuditOut:
    def _maybe_json(v: str | None):
        if v is None:
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v

    return AuditOut(
        id=row.id,
        ts=_parse_dt(row.ts),
        actor=row.actor,
        action=row.action,
        target=row.target,
        before=_maybe_json(row.before),
        after=_maybe_json(row.after),
        ip=row.ip,
    )


def _parse_dt(value: str | None) -> datetime:
    """Parst ISO-Datum oder gibt epoch zurueck."""
    if not value:
        return datetime.fromtimestamp(0)
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromtimestamp(0)
