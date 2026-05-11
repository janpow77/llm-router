-- Migration 003: Dynamic Spoke Registration + Fallback-URL
--
-- Erweitert admin_spokes um:
--   - source:        'manual' (admin-UI) | 'dynamic' (self-registered)
--   - last_seen_at:  Heartbeat-Timestamp fuer dynamic spokes
--   - version:       optionale Spoke-Version (z.B. egpu-managerd-Build)
--   - fallback_url:  optionaler sekundaerer Endpoint fuer Auto-Failover
--
-- Idempotent: SQLite faengt "duplicate column" im Migration-Runner ab
-- (siehe admin/db.py).

ALTER TABLE admin_spokes ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE admin_spokes ADD COLUMN last_seen_at TEXT;
ALTER TABLE admin_spokes ADD COLUMN version TEXT;
ALTER TABLE admin_spokes ADD COLUMN fallback_url TEXT;

-- Bestehende Zeilen explizit auf 'manual' setzen (DEFAULT greift nur fuer
-- neue Zeilen — fuer schon existierende ist source = NULL nach ADD COLUMN
-- in SQLite-Versionen ohne Stored-Default; sicherheitshalber UPDATE).
UPDATE admin_spokes SET source = 'manual' WHERE source IS NULL OR source = '';
