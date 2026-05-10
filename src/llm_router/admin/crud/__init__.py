"""CRUD-Layer fuer das Admin-Backend.

Pro Resource ein Modul. Alle Funktionen nehmen eine Session und schreiben
Audit-Eintraege via ``services.audit_log.write_audit``.
"""
