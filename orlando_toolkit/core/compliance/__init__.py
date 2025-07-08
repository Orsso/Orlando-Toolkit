"""Post-conversion compliance helpers.

Each helper exposes a single ``apply(context: DitaContext) -> None`` function
that mutates *context* in-place to satisfy a specific Orlando DITA rule set.

The helpers are intentionally tiny and single-responsibility so they remain
maintainable and easy to test in isolation.
"""

from __future__ import annotations

from .metadata_builder import apply as build_metadata  # noqa: F401
from .topicmeta_enricher import apply as enrich_topicmeta  # noqa: F401
from .id_generator import apply as ensure_ids  # noqa: F401
from .prolog_normalizer import apply as normalize_prolog  # noqa: F401

__all__ = [
    "build_metadata",
    "enrich_topicmeta",
    "ensure_ids",
    "normalize_prolog",
]
