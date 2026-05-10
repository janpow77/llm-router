"""API-Key-Generierung, Hashing und Verifikation.

Format der ausgegebenen Keys:
    ``<prefix>_<32-byte url-safe base64>``

- ``prefix``: Default ``llmr``, ableitbar aus dem App-Namen
- Hash: SHA-256 (deterministisch). Vergleich mit ``secrets.compare_digest``.
- Speicherung: ``api_key_hash`` (Hex), ``api_key_preview`` (erste 4 + ``...`` + letzte 4 Zeichen)
"""
from __future__ import annotations

import hashlib
import re
import secrets

_PREFIX_RE = re.compile(r"[^a-z0-9]+")
_SECRET_BYTES = 24  # ergibt 32 base64-Zeichen


def derive_prefix(app_name: str, default: str = "llmr") -> str:
    """Erzeugt ein kurzes Prefix aus dem App-Namen, max 12 Zeichen, lowercase."""
    cleaned = _PREFIX_RE.sub("", app_name.lower())
    if not cleaned:
        return default
    return cleaned[:12]


def generate_api_key(app_name: str | None = None) -> str:
    """Erzeugt einen kryptographisch sicheren API-Key inkl. Prefix."""
    prefix = derive_prefix(app_name or "")
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return f"{prefix}_{secret}"


def hash_api_key(api_key: str) -> str:
    """SHA-256-Hex des Keys (deterministisch — kompatibel zur Lookup-Tabelle)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(plain: str, expected_hash: str) -> bool:
    """Konstantzeit-Vergleich Hash(plain) == expected_hash."""
    if not plain or not expected_hash:
        return False
    actual = hash_api_key(plain)
    return secrets.compare_digest(actual, expected_hash)


def preview(api_key: str) -> str:
    """Liefert eine sichere Vorschau, z.B. ``ad_••••f4a2``."""
    if "_" in api_key:
        prefix, secret = api_key.split("_", 1)
    else:
        prefix, secret = "", api_key
    if len(secret) < 4:
        return f"{prefix}_••••" if prefix else "••••"
    last4 = secret[-4:]
    if prefix:
        return f"{prefix}_••••{last4}"
    return f"••••{last4}"
