"""Config-Loader für llm-router (YAML-basiert).

Schema (siehe config.example.yaml):

    server:
      host: 0.0.0.0
      port: 7842
      version: 0.1.0

    apps:
      - id: auditworkshop
        api_key: optional-secret
        rate_limit_rpm: 120
        max_concurrent: 8
      - id: default
        # Fallback wenn X-App-Id fehlt UND allow_default = true
        api_key: null
        rate_limit_rpm: 30
        max_concurrent: 2

    auth:
      require_app_id: true
      allow_default: true
      api_key_required: false

    spokes:
      - name: nuc-egpu
        url: http://100.102.132.11:11434
        scheme: ollama          # zukünftig: openai, anthropic ...
        weight: 1
        timeout_s: 300

    routes:
      - model_glob: "*"
        spoke: nuc-egpu

    metrics:
      db_path: /data/metrics.db
      retention_days: 30
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    id: str
    api_key: str | None = None
    rate_limit_rpm: int = 60
    max_concurrent: int = 4
    description: str = ""


@dataclass
class SpokeConfig:
    name: str
    url: str
    scheme: str = "ollama"
    weight: int = 1
    timeout_s: int = 300
    # Optionaler sekundaerer Endpoint fuer Auto-Failover. Wenn primary 3x in
    # Folge timeoutet/502/503/504 liefert, proxiert der Router temporaer an
    # diese URL. Circuit-Breaker reset nach 5 erfolgreichen primary-Calls.
    fallback_url: str | None = None


@dataclass
class RouteRule:
    model_glob: str
    spoke: str


@dataclass
class AuthConfig:
    require_app_id: bool = True
    allow_default: bool = True
    api_key_required: bool = False


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 7842
    version: str = "0.1.0"


@dataclass
class MetricsConfig:
    db_path: str = "/data/metrics.db"
    retention_days: int = 30


@dataclass
class RouterConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    apps: list[AppConfig] = field(default_factory=list)
    spokes: list[SpokeConfig] = field(default_factory=list)
    routes: list[RouteRule] = field(default_factory=list)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    def app_by_id(self, app_id: str) -> AppConfig | None:
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def spoke_by_name(self, name: str) -> SpokeConfig | None:
        for spoke in self.spokes:
            if spoke.name == name:
                return spoke
        return None

    def route_for_model(self, model: str) -> SpokeConfig | None:
        """Erste passende Routing-Regel anwenden (glob-basiert)."""
        from fnmatch import fnmatch

        for rule in self.routes:
            if fnmatch(model or "", rule.model_glob):
                return self.spoke_by_name(rule.spoke)
        # Fallback: erster Spoke
        return self.spokes[0] if self.spokes else None


def load_config(path: str | Path | None = None) -> RouterConfig:
    """Lädt Config aus YAML. Pfad-Resolution-Reihenfolge:
    1. Argument
    2. Env LLM_ROUTER_CONFIG
    3. /etc/llm-router/config.yaml
    4. ./config.yaml
    """
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    if env_path := os.environ.get("LLM_ROUTER_CONFIG"):
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path("/etc/llm-router/config.yaml"),
            Path("config.yaml"),
            Path(__file__).resolve().parent.parent.parent / "config.example.yaml",
        ]
    )

    config_path: Path | None = None
    for cand in candidates:
        if cand.exists():
            config_path = cand
            break

    if not config_path:
        log.warning("Keine Config-Datei gefunden, nutze Defaults.")
        return RouterConfig()

    log.info("Lade Config: %s", config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    server = ServerConfig(**(raw.get("server") or {}))
    auth = AuthConfig(**(raw.get("auth") or {}))
    metrics = MetricsConfig(**(raw.get("metrics") or {}))
    apps = [AppConfig(**a) for a in (raw.get("apps") or [])]
    spokes = [SpokeConfig(**s) for s in (raw.get("spokes") or [])]
    routes = [RouteRule(**r) for r in (raw.get("routes") or [])]

    return RouterConfig(
        server=server,
        auth=auth,
        apps=apps,
        spokes=spokes,
        routes=routes,
        metrics=metrics,
    )
