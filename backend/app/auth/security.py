"""Backwards-compatible re-export.

Hashing and token logic live in app.core.security. This module previously held
a second copy of both; it now re-exports the canonical implementation so
existing imports keep working.
"""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
