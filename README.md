# llm-router

Zentraler LLM-Routing-Hub für die Workshop-Plattform. Empfängt Ollama- und
OpenAI-kompatible Requests, identifiziert die Quell-App über `X-App-Id`,
sammelt Stats in SQLite und proxied an einen oder mehrere GPU-Spokes.

> Status: **Phase 1** — single-spoke, in-memory rate limiting, read-only
> Dashboard. Multi-Spoke + Failover folgen in Phase 2.

## Architektur

```
   ┌──────────────────────────────────────────────────────────┐
   │  Apps (auditworkshop, audit_designer, flowinvoice, …)    │
   │  Header: X-App-Id, optional X-Api-Key                    │
   └───────────────────────┬──────────────────────────────────┘
                           │  Ollama-Schema (/api/*) oder
                           │  OpenAI-Schema (/v1/*)
                           ▼
              ┌────────────────────────────┐
              │       llm-router           │
              │   FastAPI · Port 7842      │
              │  ┌──────────────────────┐  │
              │  │ Ident → Rate-Limit   │  │
              │  │ → Routing → Proxy    │  │
              │  │ → Metrics (SQLite)   │  │
              │  └──────────────────────┘  │
              │  /admin/  Dashboard        │
              └─────────────┬──────────────┘
                            │  HTTP Streaming-Proxy (httpx)
                            ▼
                ┌──────────────────────────┐
                │   Spoke: nuc-egpu        │
                │   100.102.132.11:11434   │
                │   Ollama + qwen3:14b     │
                └──────────────────────────┘
```

## API

### Ollama-kompatibel
| Pfad                  | Methode | Verhalten                          |
|-----------------------|---------|------------------------------------|
| `/api/generate`       | POST    | streamt 1:1, parst `eval_count`     |
| `/api/chat`           | POST    | streamt 1:1                         |
| `/api/embeddings`     | POST    | proxiert                            |
| `/api/embed`          | POST    | proxiert                            |
| `/api/tags`           | GET     | proxiert                            |
| `/api/show`           | POST    | proxiert                            |
| `/api/version`        | GET     | proxiert                            |

### OpenAI-kompatibel
| Pfad                       | Methode | Verhalten                |
|----------------------------|---------|--------------------------|
| `/v1/chat/completions`     | POST    | streamt SSE 1:1, parst `usage` |
| `/v1/completions`          | POST    | proxiert                  |
| `/v1/embeddings`           | POST    | proxiert                  |
| `/v1/models`               | GET     | proxiert                  |

### Admin (read-only)
| Pfad                | Beschreibung                                     |
|---------------------|--------------------------------------------------|
| `/admin/`           | Dashboard (HTML + Tailwind via CDN)              |
| `/admin/stats`      | Aggregierte Stats (24h)                          |
| `/admin/apps`       | Konfigurierte Apps                               |
| `/admin/logs`       | Letzte 50 Requests                               |
| `/admin/spokes`     | Health-Check aller Spokes                        |
| `/admin/metrics`    | Prometheus-kompatibler Plaintext-Export          |
| `/health`           | Liveness + Spoke-Health                          |
| `/docs`             | OpenAPI Swagger-UI                               |

## Identifikation

Jede App muss sich per Header identifizieren:

```http
X-App-Id: auditworkshop
X-Api-Key: <optional, falls in Config gesetzt>
```

- Wenn `auth.allow_default = true` und kein Header gesetzt → fallback auf
  App-ID `default`. So kann man schnell mit `curl` testen ohne 401 zu sehen.
- Wenn `auth.api_key_required = true` und die App einen `api_key` in der
  Config hat → wird gegen `X-Api-Key` validiert.

## Rate-Limiting

Pro App in Config:

```yaml
- id: auditworkshop
  rate_limit_rpm: 120     # Requests pro Minute (Sliding Window)
  max_concurrent: 8       # gleichzeitige Inflight-Requests
```

Bei Limit: HTTP `429` mit `Retry-After`-Header.

## Metrics

Pro Request werden gespeichert (SQLite, WAL-Modus):
`ts, app_id, route, model, prompt_tokens, completion_tokens, duration_ms,
http_status, spoke, error`.

Aggregations-Helfer in `MetricsStore`:
- `requests_per_app_last(hours)`
- `top_models(hours, limit)`
- `latency_buckets(hours)` — 6 fixe Buckets von <100ms bis >60s
- `recent_logs(limit)`
- `prune(retention_days)` — manuelles Pruning

## Config

Vollständiges Beispiel: `config.example.yaml`. Schema in `src/llm_router/config.py`.

### Neue App hinzufügen

```yaml
apps:
  - id: meinprojekt
    description: "Beschreibung"
    api_key: null                   # oder: "secret-string"
    rate_limit_rpm: 120
    max_concurrent: 4
```

### Neuen Spoke hinzufügen

```yaml
spokes:
  - name: zweite-gpu
    url: http://100.x.y.z:11434
    scheme: ollama
    timeout_s: 300

routes:
  # bestimmtes Modell auf neuen Spoke routen:
  - model_glob: "llama3.1:70b"
    spoke: zweite-gpu
  # Fallback bleibt:
  - model_glob: "*"
    spoke: nuc-egpu
```

> Routing-Regeln werden in Reihenfolge ausgewertet (erstes Match gewinnt).

## Lokal entwickeln

```bash
cd /home/janpow/Projekte/llm-router
docker build -t llm-router:dev .
docker run --rm -p 7842:7842 \
  -v $(pwd)/config.example.yaml:/etc/llm-router/config.yaml \
  -v $(pwd)/.devdata:/data \
  llm-router:dev

# Smoke-Tests
pip install -e ".[dev]"
pytest tests/ -v

# Manuell:
curl -s -H "X-App-Id: test" http://localhost:7842/api/tags
curl -s -H "X-App-Id: test" -X POST http://localhost:7842/api/generate \
  -d '{"model":"qwen3:14b","prompt":"Sag hi.","stream":false}'

open http://localhost:7842/admin/
```

## Deployment auf CCX23

Image lokal bauen, via Tailscale-SCP transferieren, `docker load` + Compose hoch.

```bash
docker build -t llm-router:dev .
docker save llm-router:dev | gzip > /tmp/llm-router-image.tar.gz
scp /tmp/llm-router-image.tar.gz deploy@100.99.159.80:/tmp/

ssh deploy@100.99.159.80 'sudo bash -s' <<'REMOTE'
mkdir -p /opt/llm-router /etc/llm-router /var/lib/llm-router/data
zcat /tmp/llm-router-image.tar.gz | docker load
# Config liegt unter /etc/llm-router/config.yaml
cd /opt/llm-router && docker compose -f compose.yaml up -d
docker ps --filter name=llm-router
REMOTE
```

Aktualisierung = neues Image bauen + `docker save | scp + load + docker compose up -d`.

## Workshop-Backend Integration

Heute ist das Workshop-Backend direkt mit dem NUC-Ollama verbunden. Der
Router-Pfad ist *vorbereitet, aber nicht aktiv*. Siehe
`HETZNER_LLM_ROUTER_SWITCH.md` (auf CCX23 unter `/opt/auditworkshop/`).

## Bekannte Limits (Phase 1)

- **Single-Spoke** — kein Failover wenn NUC offline. Geplant: Liste von
  Spokes pro Routing-Regel mit Health-basiertem Auswahl.
- **In-Memory Rate-Limit** — bei mehreren Router-Replicas würden die
  Limits divergieren. Heute: 1 Replica.
- **Kein Auth-Frontend** — `X-Api-Key` ist optional und wird nur geprüft
  wenn aktiv konfiguriert. Schutz heute: Tailscale-only / Caddy-Basic-Auth.
- **Token-Counts opportunistisch** — wir parsen Ollama `eval_count` und
  OpenAI `usage`, aber ohne diese Felder bleibt der Wert `null`.
- **Pruning manuell** — `DELETE /admin/logs/older-than-days/{days}`. Cron
  kommt in Phase 2.
- **Kein Modell-Lifecycle** — der Router lädt/entlädt nichts. Macht der
  egpu-managerd auf der NUC.
