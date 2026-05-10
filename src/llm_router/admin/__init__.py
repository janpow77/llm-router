"""Admin-Backend fuer den llm-router.

Enthaelt das vollwertige CRUD-Adminbackend mit Auth, Apps, Spokes, Routes,
Quotas, Audit-Log und Live-Log-Stream. Wird von ``main.py`` via
``include_router(admin_api_router)`` eingebunden.

Pfade:
- Alle Endpoints unter ``/admin/api/*``
- Eigene SQLite-DB (Default ``/data/admin.db``), unabhaengig von ``metrics.db``
"""
from .router import router as admin_api_router  # noqa: F401

__all__ = ["admin_api_router"]
