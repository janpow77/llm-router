# Admin-Backend — Integration in den llm-router

Stand: 2026-05-10

Dieses Dokument beschreibt, wie das CRUD-Admin-Backend
(`src/llm_router/admin/`) in die bestehende FastAPI-App
(`src/llm_router/main.py`) eingebunden wird.

Das Modul ist self-contained:
- eigene SQLite-DB (Default `/data/admin.db`, parallel zu `metrics.db`)
- eigener APIRouter mit Prefix `/admin/api/*`
- eigene Auth (Bearer-Token, Single-Admin-Passwort via Env)
- eigene Background-Tasks (Spoke-Health-Loop)

## 1. Patch fuer `src/llm_router/main.py`

In `lifespan()` initialisieren und Tasks starten/beenden — **5 Zeilen Code** plus Router-Include:

```python
from .admin import admin_api_router
from .admin.router import startup_admin, shutdown_admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... bestehender Code (Config, MetricsStore, Limiter) ...
    await startup_admin()           # initialisiert Admin-DB + startet Spoke-Health-Loop
    try:
        yield
    finally:
        await shutdown_admin()      # stoppt Background-Tasks sauber

# Direkt nach den anderen include_router-Aufrufen:
app.include_router(admin_api_router)
```

`startup_admin()` ist idempotent und respektiert Env-Schalter
(`ADMIN_DISABLE_HEALTH_LOOP=1` schaltet den Loop fuer Tests ab).

## 2. Environment-Variablen

| Variable                          | Default                       | Zweck                                                    |
|-----------------------------------|-------------------------------|----------------------------------------------------------|
| `LLM_ROUTER_ADMIN_PASSWORD`       | `admin` (mit Warn-Log!)       | Admin-Passwort fuer `/admin/api/auth/login`              |
| `LLM_ROUTER_SESSION_TTL_HOURS`    | `24`                          | Lebensdauer ausgegebener Bearer-Token                    |
| `ADMIN_DB_PATH`                   | `/data/admin.db`              | Pfad zur Admin-SQLite-DB                                 |
| `ADMIN_DB_URL`                    | (leer)                        | Voller SQLAlchemy-URL — uebersteuert `ADMIN_DB_PATH`     |
| `METRICS_DB_PATH`                 | `/data/metrics.db`            | Wo das Admin den Live-Log/Stats des Cores liest          |
| `ADMIN_DATA_DIR`                  | `/data`                       | Wird in `/admin/api/settings` ausgegeben                 |
| `LLM_ROUTER_CONFIG`               | `/etc/llm-router/config.yaml` | Wird in `/admin/api/settings` ausgegeben                 |
| `ADMIN_DISABLE_HEALTH_LOOP`       | (leer)                        | `=1` schaltet den periodischen Spoke-Ping ab (Tests/CI)  |

In Production (Hetzner): mindestens `LLM_ROUTER_ADMIN_PASSWORD` setzen.

## 3. Docker-Volumes

`/data` muss persistent gemountet sein. In `docker-compose.yml`:

```yaml
services:
  llm-router:
    image: llm-router:latest
    volumes:
      - llm_router_data:/data
    environment:
      LLM_ROUTER_ADMIN_PASSWORD: "${LLM_ROUTER_ADMIN_PASSWORD}"
      LLM_ROUTER_CONFIG: /etc/llm-router/config.yaml
      ADMIN_DB_PATH: /data/admin.db
      METRICS_DB_PATH: /data/metrics.db

volumes:
  llm_router_data:
```

`admin.db` und `metrics.db` koennen sich das Volume teilen.

## 4. Caddy-Konfiguration

`/admin/api/*` (REST + SSE) **und** `/admin/*` (statische SPA des
Frontend-Agents, ausgeliefert via FastAPI oder zweiter Container) muessen
beide auf den Router-Container geroutet werden:

```caddyfile
your-router.example.com {
    encode zstd gzip

    # Admin-API + SPA gehen beide an FastAPI
    handle /admin/api/* {
        reverse_proxy llm-router:7842
    }
    handle /admin/* {
        reverse_proxy llm-router:7842
    }

    # Standard-Proxy-Endpoints
    handle {
        reverse_proxy llm-router:7842
    }
}
```

**Wichtig fuer SSE** (`/admin/api/logs/stream`): Caddy puffert per Default
nicht — passt. Nginx braucht `proxy_buffering off;`.

## 5. Datenbank-Migration

Es gibt **keine separate Migration-Step**. `startup_admin()` ruft
`init_db()` auf, das die SQL-Datei
`src/llm_router/admin/migrations/001_initial.sql` idempotent einspielt
(`CREATE TABLE IF NOT EXISTS`).

Spaetere Schema-Aenderungen: einfach eine neue Datei
`migrations/002_*.sql` anlegen — sie wird bei naechstem Startup automatisch
mit eingespielt.

## 6. Beruehrte Tabellen (alle in `admin.db`)

- `admin_apps` — App-Registry (Name, Quotas, gehashter API-Key)
- `admin_spokes` — Konfigurierte Backends (Ollama / OpenAI)
- `admin_models` — Discovered Modelle pro Spoke
- `admin_routes` — Routing-Regeln (Model-Glob -> Spoke)
- `admin_quotas` — Quota-Mirror + Counter
- `admin_audit` — Audit-Log fuer alle Mutationen
- `admin_settings` — Key-Value-Settings (z.B. `log_retention_days`)
- `admin_sessions` — Aktive Bearer-Token

## 7. Verhaeltnis zum bestehenden Router-Core

Heute komplett **entkoppelt**:
- `metrics.db` wird vom Router-Core (`metrics.py`) befuellt — Admin liest nur.
- `config.yaml` (Apps/Spokes/Routes) bleibt die Live-Konfiguration des Proxys.
- Apps/Spokes in der Admin-DB sind Verwaltungs-Layer fuer das UI.

**Naechster Schritt** (separates Ticket): Der Router-Core kann ueber
`crud.apps.find_by_api_key()` Admin-DB-Apps fuer Auth nutzen und/oder
Admin-Routes als Fallback zur YAML-Config laden.

## 8. Tests

```bash
cd /home/janpow/Projekte/llm-router
PYTHONPATH=src python3 -m pytest src/llm_router/admin/tests/ -v
```

Aktuell: **37 Tests, alle gruen** (~1.8s).

## 9. Smoke-Check nach dem Patch

```bash
# Health (offen)
curl -s http://localhost:7842/admin/api/health | jq

# Login
TOKEN=$(curl -s -X POST http://localhost:7842/admin/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$LLM_ROUTER_ADMIN_PASSWORD\"}" | jq -r .token)

# Apps listen
curl -s http://localhost:7842/admin/api/apps -H "Authorization: Bearer $TOKEN" | jq
```
