"""Backwards-compatible re-export.

get_db has a single definition in app.database.session. This module previously
declared a duplicate; routes import from either path, so it now re-exports the
canonical one rather than defining a second.
"""

from app.database.session import get_db

__all__ = ["get_db"]
