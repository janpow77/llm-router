-- Initiales Schema fuer das Admin-Backend.
-- Wird beim Startup idempotent eingespielt (CREATE TABLE IF NOT EXISTS).
-- SQLite, daher TEXT fuer alle ID-Felder (ULID/UUID-Strings).

CREATE TABLE IF NOT EXISTS admin_apps (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL DEFAULT '',
    api_key_hash    TEXT NOT NULL,
    api_key_preview TEXT NOT NULL,
    allowed_models  TEXT NOT NULL DEFAULT '[]',  -- JSON-Liste
    quota_rpm       INTEGER NOT NULL DEFAULT 60,
    quota_concurrent INTEGER NOT NULL DEFAULT 4,
    quota_daily_tokens INTEGER NOT NULL DEFAULT 1000000,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_apps_name ON admin_apps(name);

CREATE TABLE IF NOT EXISTS admin_spokes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    base_url        TEXT NOT NULL,
    type            TEXT NOT NULL DEFAULT 'ollama',  -- ollama | openai
    auth_header     TEXT,                             -- z.B. "Authorization"
    auth_value      TEXT,                             -- z.B. "Bearer sk-..."
    status          TEXT NOT NULL DEFAULT 'unknown', -- online | offline | unknown
    last_check_at   TEXT,
    last_error      TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_spokes_name ON admin_spokes(name);

CREATE TABLE IF NOT EXISTS admin_models (
    id              TEXT PRIMARY KEY,           -- "<model>@<spoke_name>"
    name            TEXT NOT NULL,
    spoke_id        TEXT NOT NULL,
    spoke_name      TEXT NOT NULL,
    size_gb         REAL,
    context_length  INTEGER,
    quantization    TEXT,
    discovered_at   TEXT NOT NULL,
    FOREIGN KEY (spoke_id) REFERENCES admin_spokes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_admin_models_spoke ON admin_models(spoke_id);

CREATE TABLE IF NOT EXISTS admin_routes (
    id              TEXT PRIMARY KEY,
    model_glob      TEXT NOT NULL,
    spoke_id        TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 100,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (spoke_id) REFERENCES admin_spokes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_admin_routes_priority ON admin_routes(priority);

CREATE TABLE IF NOT EXISTS admin_quotas (
    -- Optionaler Override pro App. Falls fehlend: aus admin_apps.
    -- Bietet Platz fuer in-memory Counter-Snapshots (current_*).
    app_id              TEXT PRIMARY KEY,
    rpm                 INTEGER NOT NULL,
    concurrent          INTEGER NOT NULL,
    daily_tokens        INTEGER NOT NULL,
    current_rpm         INTEGER NOT NULL DEFAULT 0,
    current_concurrent  INTEGER NOT NULL DEFAULT 0,
    current_daily_tokens INTEGER NOT NULL DEFAULT 0,
    counter_window_start TEXT,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (app_id) REFERENCES admin_apps(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin_audit (
    id              TEXT PRIMARY KEY,
    ts              TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'admin',
    action          TEXT NOT NULL,
    target          TEXT,
    before          TEXT,                       -- JSON
    after           TEXT,                       -- JSON
    ip              TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_ts ON admin_audit(ts DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor ON admin_audit(actor);
CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit(action);

CREATE TABLE IF NOT EXISTS admin_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL               -- JSON-encoded
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token           TEXT PRIMARY KEY,
    actor           TEXT NOT NULL DEFAULT 'admin',
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    ip              TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires ON admin_sessions(expires_at);
