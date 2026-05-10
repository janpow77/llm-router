# syntax=docker/dockerfile:1.6
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

EXPOSE 7842

ENV LLM_ROUTER_CONFIG=/etc/llm-router/config.yaml \
    PYTHONPATH=/app/src

HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:7842/health || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "llm_router.main:app", "--host", "0.0.0.0", "--port", "7842", "--workers", "1"]
