# LLM-Router Admin API — Contract v1

Diese Spec ist **verbindlich für das Backend** (`/home/janpow/Projekte/llm-router/src/llm_router/`).
Frontend baut gegen genau diese Endpunkte. Bei Backend-Änderungen bitte hier zuerst dokumentieren.

## Konventionen

- **Base-Path:** `/admin/api`
- **Auth:** Header `Authorization: Bearer <token>` — Token via `POST /admin/api/auth/login` erhältlich
- **Status-Codes:**
  - `200` OK / `201` Created / `204` No Content
  - `400` Validation Error (`{detail: string}`)
  - `401` Unauthenticated → Frontend redirect `/admin/login`
  - `403` Forbidden
  - `404` Not Found
  - `409` Conflict (z.B. doppelter Name)
  - `500` Server Error
- **Pagination:** Falls notwendig per Query `?limit=N&offset=N`. Antwort als nackte Liste (kein Wrapper) für Einfachheit.
- **Datums-Format:** ISO 8601 mit `Z` (UTC), z.B. `2026-05-10T14:23:00Z`
- **IDs:** ULID/UUID-Strings

---

## Auth

### `POST /admin/api/auth/login`
**Body:** `{ "password": "..." }`
**Response (200):** `{ "token": "...", "expires_at": "2026-05-11T00:00:00Z" }`
**Response (401):** `{ "detail": "Invalid password" }`

### `POST /admin/api/auth/logout`
**Auth:** required
**Response (204):** —

### `GET /admin/api/auth/me`
**Auth:** required
**Response (200):** `{ "logged_in": true, "expires_at": "2026-05-11T00:00:00Z" }`

---

## Health

### `GET /admin/api/health`
**Response (200):**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "started_at": "2026-05-10T08:00:00Z",
  "spokes_health": [
    { "spoke_id": "nuc-egpu", "status": "online", "last_check_at": "..." }
  ]
}
```

---

## Dashboard

### `GET /admin/api/dashboard`
**Response (200):**
```json
{
  "requests_today": 18429,
  "tokens_today": 4283910,
  "errors_today": 12,
  "mean_latency_ms": 842,
  "p95_latency_ms": 2410,
  "active_apps": 4,
  "active_spokes": 1,
  "top_apps": [{ "app_id": "audit_designer", "name": "audit_designer", "count": 9421 }],
  "top_models": [{ "model": "qwen3:14b", "count": 12932 }]
}
```

### `GET /admin/api/dashboard/timeseries?bucket=1h&hours=24`
**Query:** `bucket` ∈ {`5m`,`15m`,`1h`}, `hours` ∈ [1,168]
**Response (200):**
```json
[
  { "ts": "2026-05-10T13:00:00Z", "requests": 412, "tokens": 89231, "errors": 1, "mean_latency_ms": 712 }
]
```

---

## Apps (CRUD)

### `GET /admin/api/apps`
**Response (200):** `App[]`
```json
[
  {
    "id": "app_01HXX...",
    "name": "audit_designer",
    "description": "Hauptanwendung (NUC)",
    "api_key_preview": "ad_••••f4a2",
    "allowed_models": ["qwen3:14b", "qwen3:8b"],
    "quota": { "rpm": 240, "concurrent": 16, "daily_tokens": 5000000 },
    "enabled": true,
    "request_count_today": 9421,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

### `POST /admin/api/apps`
**Body:**
```json
{
  "name": "audit_designer",
  "description": "...",
  "allowed_models": ["qwen3:14b"],
  "quota": { "rpm": 240, "concurrent": 16, "daily_tokens": 5000000 }
}
```
**Response (201):** `App` mit zusätzlichem Feld `api_key` (full, **only shown once**)

### `GET /admin/api/apps/{id}`
**Response (200):**
```json
{
  "...": "App fields",
  "recent_requests": [
    { "ts": "...", "model": "qwen3:14b", "status": "ok", "duration_ms": 821, "tokens": 1230 }
  ]
}
```

### `PATCH /admin/api/apps/{id}`
**Body:** Partial App (any subset of name, description, allowed_models, quota, enabled)
**Response (200):** updated `App`

### `DELETE /admin/api/apps/{id}`
**Response (204):** —

### `POST /admin/api/apps/{id}/rotate-key`
**Response (200):** `{ "api_key": "ad_xxxxxxxxxxxxxxxxxxxxx" }` (full, only this once)

### `POST /admin/api/apps/{id}/toggle-enabled`
**Response (200):** updated `App`

---

## Spokes (CRUD)

### `GET /admin/api/spokes`
**Response (200):** `Spoke[]`
```json
[
  {
    "id": "spk_...",
    "name": "nuc-egpu",
    "base_url": "http://100.102.132.11:11434",
    "type": "ollama",
    "status": "online",
    "last_check_at": "...",
    "models": ["qwen3:14b", "qwen3:8b", "nomic-embed-text"],
    "gpu_info": {
      "device": "NVIDIA GeForce RTX 5070 Ti",
      "vram_total_mb": 16384,
      "vram_used_mb": 14820,
      "utilization_pct": 78
    }
  }
]
```

### `POST /admin/api/spokes`
**Body:** `{ "name": "...", "base_url": "...", "type": "ollama"|"openai", "auth": { "api_key": "..." }? }`
**Response (201):** `Spoke`

### `PATCH /admin/api/spokes/{id}` — Partial update
### `DELETE /admin/api/spokes/{id}` — 204

### `POST /admin/api/spokes/{id}/health-check`
**Response (200):** `Spoke` (updated `status` + `last_check_at`)

---

## Models

### `GET /admin/api/models`
**Response (200):**
```json
[
  {
    "id": "qwen3:14b@nuc-egpu",
    "name": "qwen3:14b",
    "spoke_id": "spk_...",
    "spoke_name": "nuc-egpu",
    "size_gb": 15.2,
    "context_length": 32768,
    "quantization": "Q8_0"
  }
]
```

### `POST /admin/api/models/refresh`
**Response (200):** `{ "discovered": 12, "updated_at": "..." }`

---

## Routes (model→spoke)

### `GET /admin/api/routes`
**Response (200):** `Route[]` sortiert nach `priority` ASC
```json
[
  { "id": "rt_...", "model_glob": "qwen3:*", "spoke_id": "spk_...", "spoke_name": "nuc-egpu", "priority": 10, "enabled": true }
]
```

### `POST /admin/api/routes`
**Body:** `{ "model_glob": "*", "spoke_id": "...", "priority": 100, "enabled": true }`

### `PATCH /admin/api/routes/{id}` — Partial update
### `DELETE /admin/api/routes/{id}` — 204

---

## Quotas

### `GET /admin/api/quotas/{app_id}`
**Response (200):**
```json
{
  "app_id": "app_...",
  "limits": { "rpm": 240, "concurrent": 16, "daily_tokens": 5000000 },
  "current": { "rpm": 87, "concurrent": 4, "daily_tokens": 1283910 }
}
```

### `PATCH /admin/api/quotas/{app_id}`
**Body:** `{ "rpm"?: int, "concurrent"?: int, "daily_tokens"?: int }`
**Response (200):** Quota object (mit limits + current)

---

## Logs

### `GET /admin/api/logs?app_id=&model=&status=&limit=100&since=`
**Query:** alle optional. `since` = ISO-Timestamp.
**Response (200):**
```json
[
  {
    "ts": "...",
    "request_id": "req_...",
    "app_id": "audit_designer",
    "model": "qwen3:14b",
    "spoke_id": "spk_...",
    "status": "ok",
    "duration_ms": 821,
    "prompt_tokens": 230,
    "completion_tokens": 1000,
    "error": null
  }
]
```

### `GET /admin/api/logs/stream` (SSE)
**Auth:** Token via Query `?token=...` (SSE unterstützt keine custom headers im Browser)
**Format:** `data: {json}\n\n` pro Event.
Events ab Connect-Zeit, kein Replay.

---

## Audit-Log

### `GET /admin/api/audit?limit=200&actor=&action=&since=`
**Response (200):**
```json
[
  {
    "id": "aud_...",
    "ts": "...",
    "actor": "admin",
    "action": "app.update",
    "target": "app_...",
    "before": { "quota": { "rpm": 100 } },
    "after": { "quota": { "rpm": 240 } }
  }
]
```

---

## Settings

### `GET /admin/api/settings`
**Response (200):**
```json
{
  "router_version": "0.1.0",
  "uptime_seconds": 38291,
  "log_retention_days": 30,
  "default_quotas": { "rpm": 60, "concurrent": 4, "daily_tokens": 1000000 },
  "data_dir": "/data",
  "config_path": "/etc/llm-router/config.yaml"
}
```

### `PATCH /admin/api/settings`
**Body:** Partial. Pflicht-Felder werden serverseitig validiert.
**Response (200):** Settings object

---

## Fehler-Format (alle 4xx/5xx)
```json
{ "detail": "Beschreibung des Fehlers" }
```

Bei Validation-Errors (FastAPI):
```json
{ "detail": [{ "loc": ["body", "name"], "msg": "field required", "type": "value_error.missing" }] }
```
