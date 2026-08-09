"""Product configuration — the blueprint the factory produces and the engine reads.

See ``app.products.config`` for the design rules.

Only the leaf modules are re-exported here. ``app.products.resolver`` reads the
database and the storefront catalog, and ``app.catalog`` imports this package,
so re-exporting the resolver would close an import cycle. Import it directly:
``from app.products.resolver import resolve_config``.
"""

from app.products.config import (
    CAPABILITY_SOURCES,
    SOURCE_DECLARED,
    SOURCE_VERIFIED,
    Capability,
    Faq,
    Plan,
    ProductConfig,
    format_money,
)
from app.products.serialization import (
    ConfigParseError,
    config_from_dict,
    config_from_json,
    config_to_dict,
    config_to_json,
)

__all__ = [
    "CAPABILITY_SOURCES",
    "SOURCE_DECLARED",
    "SOURCE_VERIFIED",
    "Capability",
    "ConfigParseError",
    "Faq",
    "Plan",
    "ProductConfig",
    "config_from_dict",
    "config_from_json",
    "config_to_dict",
    "config_to_json",
    "format_money",
]
