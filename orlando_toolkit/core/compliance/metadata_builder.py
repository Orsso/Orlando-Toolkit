from __future__ import annotations

"""Populate context.metadata['topic_paths'] as required by Rule A.1."""

from pathlib import Path
from typing import Dict
from orlando_toolkit.core.models import DitaContext

__all__ = ["apply"]


def apply(context: DitaContext) -> None:  # noqa: D401
    """Ensure `topic_paths` metadata exists and is accurate.

    The validator expects a mapping of *filename* → *relative path within DATA/*.
    We assume the canonical Orlando layout: all topics live under ``topics/``.
    """

    topic_paths: Dict[str, str] = {}
    for filename in context.topics.keys():
        # Normalise path to POSIX style for consistency inside ZIPs
        topic_paths[filename] = str(Path("topics") / filename).replace("\\", "/")

    context.metadata["topic_paths"] = topic_paths
