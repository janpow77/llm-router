# syntax=docker/dockerfile:1.6

# ----------------------------------------------------------------------------
# Stage 1: Frontend-Build
# Baut das Vue-3-Admin-Dashboard und stellt /app/frontend_dist bereit.
# Idempotent: braucht nur frontend/package*.json + frontend/src/.
# ----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /work

# Lockfile vor src kopieren — Layer-Cache nutzt npm install nur bei Lock-Aenderungen.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Quellen + Build
COPY frontend/ ./
RUN npm run build

# Sanity: dist/index.html muss da sein. Wenn nicht: Build-Fehler frueh aufdecken.
RUN test -f dist/index.html || (echo "frontend build produced no dist/index.html" >&2 && exit 1)


# ----------------------------------------------------------------------------
# Stage 2: Python-Runtime mit FastAPI + statisch eingebackenem Frontend
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Minimal-Tools für Healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Editable install — schnell, klein, stable für FastAPI/httpx
RUN pip install --upgrade pip \
    && pip install -e .

# Default-Config wird via Volume gemountet, ggf. fällt das auf example zurück
COPY config.example.yaml /app/config.example.yaml

# Admin-SPA: aus Stage 1 kopiert. Garantiert vorhanden, kein optional.
# main.py haelt zusaetzlich einen Soft-Fallback bereit, falls jemand das
# Verzeichnis manuell leert (Container startet, nur Admin-API reachable).
COPY --from=frontend-build /work/dist /app/frontend_dist

EXPOSE 7842

ENV LLM_ROUTER_CONFIG=/etc/llm-router/config.yaml \
    PYTHONPATH=/app/src

HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:7842/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "llm_router.main:app", "--host", "0.0.0.0", "--port", "7842", "--workers", "1"]
