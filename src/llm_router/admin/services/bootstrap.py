"""Bootstrap-Service: füllt admin-DB beim ersten Start mit Default-Spokes.

Quellen:
1. ``llm_router.config.RouterConfig`` — Spokes aus ``config.yaml`` (falls geladen).
2. Hardcoded Defaults — z.B. NUC ``egpu-managerd`` als GPU-Workload-Hub.

Idempotent: legt einen Spoke nur an, wenn noch keiner mit dem gleichen Namen existiert.
Wird einmalig im ``startup_admin()``-Lifespan gerufen.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from ..crud import spokes as crud_spokes
from ..models import SpokeCreate

if TYPE_CHECKING:  # pragma: no cover
    pass

log = logging.getLogger(__name__)


# Hardcoded Default-Spokes: werden registriert wenn (a) kein Spoke gleichen Namens existiert
# und (b) Env LLM_ROUTER_BOOTSTRAP_DEFAULTS != "0".
#
# Naming-Konvention:
#   <host>-<kind>
# Kind:
#   - "ollama"           direkter Ollama-Endpoint (kein Lease-Tracking)
#   - "gpu-llm-manager"  zentraler GPU-/LLM-Lifecycle-Manager (vormals egpu-manager).
#                        Kümmert sich um Modell-Swap, Lease, Multi-GPU-Zuweisung.
#                        Läuft auf NUC + evo + ggf. Desktop.
#
# Priorität: niedriger = bevorzugt. gpu-llm-manager priorisiert vor direktem
# Ollama, weil er Lease-Tracking + Cross-Host-Routing macht.
DEFAULT_SPOKES: list[dict] = [
    # Wichtig: gpu-llm-manager spricht NICHT die Ollama-/OpenAI-API selbst.
    # Er ist ein Lifecycle-/Lease-Coordinator (siehe egpu-managerd /api/status,
    # /api/gpu/acquire usw.). Daher capability = ["compute"] — er wird nicht
    # fuer LLM-/Embedding-Inference geroutet, sondern erscheint in der UI als
    # Verwaltungs-Backend fuer GPU-Workloads.
    #
    # Die Ollama-Spokes (auf gleichem Host) bedienen LLM + Embedding und
    # bekommen die niedrigere Routing-Priority fuer diese Capabilities.
    {
        "name": "nuc-gpu-llm-manager",
        "base_url": "http://100.102.132.11:7842",
        "type": "gpu-llm-manager",
        "capabilities": ["compute"],
        "tags": ["nuc", "gpu", "rtx5070ti", "egpu", "lifecycle"],
        "priority": 50,
    },
    {
        "name": "nuc-ollama",
        "base_url": "http://100.102.132.11:11434",
        "type": "ollama",
        "capabilities": ["llm", "embedding"],
        "tags": ["nuc", "gpu", "rtx5070ti", "ollama"],
        "priority": 100,
    },
    {
        "name": "evo-gpu-llm-manager",
        "base_url": "http://100.81.4.99:7842",
        "type": "gpu-llm-manager",
        "capabilities": ["compute"],
        "tags": ["evo", "desktop", "rtx5070", "rtx5060", "multi-gpu"],
        "priority": 60,
    },
    {
        "name": "evo-ollama",
        "base_url": "http://100.81.4.99:11434",
        "type": "ollama",
        "capabilities": ["llm", "embedding"],
        "tags": ["evo", "desktop", "ollama"],
        "priority": 110,
    },
]


def bootstrap_spokes(session: Session, *, router_config=None) -> int:
    """Bootstrappe Spokes in die admin-DB.

    Reihenfolge:
    1. Aus ``router_config.spokes`` (YAML-Konfiguration), wenn geliefert
    2. Aus ``DEFAULT_SPOKES`` (Hardcoded GPU-Spokes)

    Returns: Anzahl neu angelegter Spokes.
    """
    if os.environ.get("LLM_ROUTER_BOOTSTRAP_DEFAULTS", "1") == "0":
        log.info("Bootstrap deaktiviert via Env LLM_ROUTER_BOOTSTRAP_DEFAULTS=0")
        return 0

    created = 0
    seen_names = {row.name for row in crud_spokes.list_spokes(session)}

    # 1. YAML-Spokes uebernehmen
    if router_config is not None:
        for s in getattr(router_config, "spokes", []):
            if s.name in seen_names:
                continue
            try:
                payload = SpokeCreate(
                    name=s.name,
                    base_url=s.url,
                    type=s.scheme if s.scheme in ("ollama", "openai", "gpu-llm-manager") else "custom",
                    capabilities=["llm"],  # YAML kennt das Feld nicht — sicherer Default
                    tags=["yaml-imported"],
                    priority=100,
                )
                crud_spokes.create_spoke(session, payload, ip="bootstrap")
                seen_names.add(s.name)
                created += 1
                log.info("Spoke aus YAML registriert: %s (%s)", s.name, s.url)
            except Exception as exc:  # noqa: BLE001
                log.warning("Konnte YAML-Spoke %s nicht registrieren: %s", s.name, exc)

    # 2. Hardcoded Defaults
    for spec in DEFAULT_SPOKES:
        if spec["name"] in seen_names:
            continue
        try:
            payload = SpokeCreate(**spec)
            crud_spokes.create_spoke(session, payload, ip="bootstrap")
            seen_names.add(spec["name"])
            created += 1
            log.info(
                "Default-Spoke registriert: %s (%s, capabilities=%s)",
                spec["name"], spec["base_url"], spec["capabilities"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Konnte Default-Spoke %s nicht registrieren: %s", spec["name"], exc)

    return created
