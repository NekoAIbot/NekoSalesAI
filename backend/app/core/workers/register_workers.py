"""Backwards-compatible re-export.

This module previously declared its own register_workers() that imported six
modules which do not exist (app.core.workers.lead_conversion and friends — the
real ones live in app.workers), so importing it always raised
ModuleNotFoundError. It also called runtime.register(), which WorkerRuntime
does not define. The working implementation is app.core.workers.registry.
"""

from app.core.workers.registry import register_workers

__all__ = ["register_workers"]
