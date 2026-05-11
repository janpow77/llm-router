"""Conftest fuer den Router-Core-Test-Suite.

Setzt vor App-Import die Admin-DB-Pfade auf temp und schaltet den
Spoke-Health-Loop ab — sonst scheitert der App-Import an fehlenden
/data-Volumes.
"""
import os
import sys
import tempfile
from pathlib import Path

# sys.path Bootstrap fuer Test-Module die llm_router importieren ohne
# Editable-Install (zur Vermeidung des bekannten ModuleNotFoundError).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_TMP = tempfile.mkdtemp(prefix="llm-router-tests-")
os.environ.setdefault("ADMIN_DB_PATH", f"{_TMP}/admin.db")
os.environ.setdefault("METRICS_DB_PATH", f"{_TMP}/metrics.db")
os.environ.setdefault("ADMIN_DATA_DIR", _TMP)
os.environ.setdefault("ADMIN_DISABLE_HEALTH_LOOP", "1")
os.environ.setdefault("LLM_ROUTER_ADMIN_PASSWORD", "test-password")
