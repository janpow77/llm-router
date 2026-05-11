-- Migration 002: Spoke-Capabilities + GPU-Info
--
-- Erweitert admin_spokes um Multi-Workload-Felder. Idempotent: SQLite
-- unterstuetzt vor 3.35 kein "ADD COLUMN IF NOT EXISTS" — der Migration-
-- Runner faengt "duplicate column"-Fehler ab und ueberspringt diese
-- Statements (siehe admin/db.py).

ALTER TABLE admin_spokes ADD COLUMN capabilities TEXT;
ALTER TABLE admin_spokes ADD COLUMN tags TEXT;
ALTER TABLE admin_spokes ADD COLUMN gpu_info TEXT;
ALTER TABLE admin_spokes ADD COLUMN priority INTEGER NOT NULL DEFAULT 100;

-- Bestehende Zeilen auf Default-Capability "llm" setzen.
UPDATE admin_spokes SET capabilities = '["llm"]' WHERE capabilities IS NULL OR capabilities = '';
UPDATE admin_spokes SET tags = '[]' WHERE tags IS NULL OR tags = '';
