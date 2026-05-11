"""Runtime-Configuration: Admin-DB als Source-of-Truth fuer Apps/Spokes/Routes.

Der Router-Core (config.py / RouterConfig) liefert YAML-Defaults beim Start.
Diese Datei stellt einen Live-Override aus der Admin-DB bereit:

- Apps (incl. API-Key-Hash-Lookup) → Authentifizierung
- Spokes (incl. Capabilities, Priority, enabled-Flag) → Routing-Pool
- Routes (model_glob → spoke) → Routing-Regeln

Der Store haelt einen kompletten In-Memory-Snapshot der admin-DB (typischerweise
< 100 Eintraege fuer Apps + Spokes + Routes zusammen) und wird:

- beim Start einmalig gefuellt
- bei jeder Admin-Mutation invalidiert/neu geladen (siehe admin/router.py)
- bei "kalter" Anfrage (Cache leer) lazily neu geladen

Fallback: wenn admin-DB leer oder nicht erreichbar, nutzt identify_app/route_for_model
die YAML-RouterConfig als Default. So bleibt der Router lebensfaehig auch wenn
die Admin-DB ausfaellt.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from fnmatch import fnmatch

from .config import AppConfig, RouterConfig, SpokeConfig

log = logging.getLogger(__name__)


@dataclass
class RuntimeApp:
    """Snapshot eines Admin-Apps fuer den Router-Core."""
    id: str           # interner DB-id (app_<uuid>)
    name: str         # menschenlesbarer App-Name (= alter "app_id" aus YAML)
    api_key_hash: str | None
    rate_limit_rpm: int
    max_concurrent: int
    enabled: bool

    def to_app_config(self) -> AppConfig:
        return AppConfig(
            id=self.name,
            api_key=None,  # Vergleich erfolgt ueber api_key_hash, nicht plain
            rate_limit_rpm=self.rate_limit_rpm,
            max_concurrent=self.max_concurrent,
            description="",
        )


@dataclass
class RuntimeSpoke:
    """Snapshot eines Admin-Spokes fuer den Router-Core."""
    id: str
    name: str
    base_url: str
    type: str
    capabilities: list[str]
    priority: int
    enabled: bool
    auth_header: str | None = None
    auth_value: str | None = None
    # Phase 3
    status: str = "unknown"
    source: str = "manual"
    fallback_url: str | None = None

    def to_spoke_config(self) -> SpokeConfig:
        # type "gpu-llm-manager" mappen wir auf "ollama"-Schema fuer den Proxy,
        # weil Workshop & co. Ollama-Schema sprechen und egpu-managerd das auch
        # akzeptiert (es proxiert intern an Ollama). Custom/paddle-ocr behalten
        # ihren Typ — der Proxy nutzt das raw-passthrough.
        scheme = self.type
        if self.type == "gpu-llm-manager":
            scheme = "ollama"
        return SpokeConfig(
            name=self.name,
            url=self.base_url,
            scheme=scheme,
            weight=1,
            timeout_s=300,
            fallback_url=self.fallback_url,
        )


@dataclass
class RuntimeRoute:
    """Snapshot einer Admin-Route."""
    id: str
    model_glob: str
    spoke_id: str  # FK in admin_spokes.id
    priority: int
    enabled: bool


@dataclass
class RuntimeConfigSnapshot:
    """In-Memory-Snapshot. Wird atomic ausgetauscht (immutable Snapshot-Pointer)."""
    apps_by_name: dict[str, RuntimeApp] = field(default_factory=dict)
    apps_by_key_hash: dict[str, RuntimeApp] = field(default_factory=dict)
    spokes_by_name: dict[str, RuntimeSpoke] = field(default_factory=dict)
    spokes_by_id: dict[str, RuntimeSpoke] = field(default_factory=dict)
    routes_sorted: list[RuntimeRoute] = field(default_factory=list)  # nach priority asc
    loaded_at: float = 0.0
    is_empty: bool = True


# ----------------------------- Globaler Store ------------------------------


_lock = threading.RLock()
_snapshot: RuntimeConfigSnapshot = RuntimeConfigSnapshot()
_yaml_fallback: RouterConfig | None = None


def set_yaml_fallback(cfg: RouterConfig) -> None:
    """Wird einmalig im Startup gesetzt (RouterConfig aus config.yaml)."""
    global _yaml_fallback
    with _lock:
        _yaml_fallback = cfg


def reload_from_admin_db() -> RuntimeConfigSnapshot:
    """Liest den aktuellen Stand der admin-DB und ersetzt den Snapshot.

    Wird nach jeder mutierenden Admin-Operation gerufen + beim Startup.
    """
    global _snapshot
    import time

    try:
        from .admin.db import get_session_factory
        from .admin.models import AppRow, RouteRow, SpokeRow
    except ImportError:
        log.warning("Admin-Modul nicht verfuegbar — RuntimeConfig bleibt leer (YAML-Fallback aktiv).")
        return _snapshot

    apps_by_name: dict[str, RuntimeApp] = {}
    apps_by_key_hash: dict[str, RuntimeApp] = {}
    spokes_by_name: dict[str, RuntimeSpoke] = {}
    spokes_by_id: dict[str, RuntimeSpoke] = {}
    routes: list[RuntimeRoute] = []

    try:
        factory = get_session_factory()
        with factory() as session:
            for row in session.query(AppRow).all():
                app = RuntimeApp(
                    id=row.id,
                    name=row.name,
                    api_key_hash=row.api_key_hash or None,
                    rate_limit_rpm=row.quota_rpm,
                    max_concurrent=row.quota_concurrent,
                    enabled=bool(row.enabled),
                )
                apps_by_name[app.name] = app
                if app.api_key_hash:
                    apps_by_key_hash[app.api_key_hash] = app

            for row in session.query(SpokeRow).all():
                import json
                caps_raw = row.capabilities or '["llm"]'
                try:
                    caps = json.loads(caps_raw) if isinstance(caps_raw, str) else list(caps_raw)
                except (TypeError, ValueError):
                    caps = ["llm"]
                spk = RuntimeSpoke(
                    id=row.id,
                    name=row.name,
                    base_url=row.base_url,
                    type=row.type,
                    capabilities=caps,
                    priority=row.priority or 100,
                    enabled=bool(row.enabled),
                    auth_header=row.auth_header,
                    auth_value=row.auth_value,
                    status=row.status or "unknown",
                    source=getattr(row, "source", None) or "manual",
                    fallback_url=getattr(row, "fallback_url", None),
                )
                spokes_by_name[spk.name] = spk
                spokes_by_id[spk.id] = spk

            for row in session.query(RouteRow).order_by(RouteRow.priority.asc()).all():
                routes.append(
                    RuntimeRoute(
                        id=row.id,
                        model_glob=row.model_glob,
                        spoke_id=row.spoke_id,
                        priority=row.priority,
                        enabled=bool(row.enabled),
                    )
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("RuntimeConfig-Reload fehlgeschlagen: %s — alter Snapshot bleibt aktiv.", exc)
        return _snapshot

    new_snap = RuntimeConfigSnapshot(
        apps_by_name=apps_by_name,
        apps_by_key_hash=apps_by_key_hash,
        spokes_by_name=spokes_by_name,
        spokes_by_id=spokes_by_id,
        routes_sorted=sorted(routes, key=lambda r: r.priority),
        loaded_at=time.time(),
        is_empty=not (apps_by_name or spokes_by_name),
    )
    with _lock:
        _snapshot = new_snap
    log.info(
        "RuntimeConfig reloaded: %d apps, %d spokes, %d routes (admin-DB authoritative=%s)",
        len(apps_by_name), len(spokes_by_name), len(routes), not new_snap.is_empty,
    )
    return new_snap


def snapshot() -> RuntimeConfigSnapshot:
    """Liefert den aktuellen Snapshot (read-only)."""
    return _snapshot


# ----------------------------- Lookups -------------------------------------


def app_by_name(name: str) -> AppConfig | None:
    """Sucht App nach Name. Erst admin-DB, dann YAML-Fallback."""
    snap = _snapshot
    if name in snap.apps_by_name:
        return snap.apps_by_name[name].to_app_config()
    if _yaml_fallback:
        return _yaml_fallback.app_by_id(name)
    return None


def app_by_api_key(plain_key: str) -> AppConfig | None:
    """Sucht App ueber den Klartext-API-Key (per Hash-Vergleich).

    Wenn der Key nicht gefunden wird in der admin-DB, faellt auf YAML zurueck
    (dort liegt der Key im Klartext, gleicher Vergleich).
    """
    if not plain_key:
        return None
    from .admin.services.api_key import hash_api_key

    h = hash_api_key(plain_key)
    snap = _snapshot
    runtime_app = snap.apps_by_key_hash.get(h)
    if runtime_app is not None:
        return runtime_app.to_app_config()
    if _yaml_fallback:
        for app in _yaml_fallback.apps:
            if app.api_key and app.api_key == plain_key:
                return app
    return None


def spoke_by_name(name: str) -> SpokeConfig | None:
    snap = _snapshot
    spk = snap.spokes_by_name.get(name)
    if spk is not None and spk.enabled:
        return spk.to_spoke_config()
    if _yaml_fallback:
        return _yaml_fallback.spoke_by_name(name)
    return None


def _spoke_is_routable(spoke: RuntimeSpoke) -> bool:
    """Spoke darf in Routing aufgenommen werden wenn enabled + nicht offline.

    'unknown' Status ist erlaubt (erster Health-Check noch nicht durch).
    Dynamische Spokes mit abgelaufenem Heartbeat sind 'offline' — die
    werden ueber den status-Filter ausgeschlossen.
    """
    return spoke.enabled and spoke.status != "offline"


def route_for_model(model: str, capability: str = "llm") -> SpokeConfig | None:
    """Findet den passenden Spoke fuer ein Modell.

    Reihenfolge:
    1. Admin-DB-Routes (priority asc, glob-match)
    2. Admin-DB-Spokes mit passender Capability (priority asc, enabled, online)
    3. YAML-Fallback

    Offline-Spokes (status='offline' — typisch nach Heartbeat-Timeout fuer
    dynamic Spokes) werden in Schritt 1/2 uebersprungen.
    """
    snap = _snapshot

    # 1. Explizite Admin-Routes
    for rule in snap.routes_sorted:
        if not rule.enabled:
            continue
        if not fnmatch(model or "", rule.model_glob):
            continue
        spk = snap.spokes_by_id.get(rule.spoke_id)
        if spk is not None and _spoke_is_routable(spk) and capability in spk.capabilities:
            return spk.to_spoke_config()

    # 2. Capability-basiertes Auto-Routing — nimm den Spoke mit niedrigster
    # Priority, der die Capability bietet und enabled+nicht offline ist.
    candidates = [
        s for s in snap.spokes_by_name.values()
        if _spoke_is_routable(s) and capability in s.capabilities
    ]
    if candidates:
        candidates.sort(key=lambda s: s.priority)
        return candidates[0].to_spoke_config()

    # 3. YAML-Fallback
    if _yaml_fallback:
        return _yaml_fallback.route_for_model(model)

    return None


def is_authoritative() -> bool:
    """True wenn admin-DB Apps/Spokes enthaelt — sonst YAML-Modus."""
    return not _snapshot.is_empty
