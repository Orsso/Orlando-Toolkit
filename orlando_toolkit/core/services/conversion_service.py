from __future__ import annotations

"""High-level conversion service for DOCX to DITA transformation.

Entry-point for any front-end (GUI, CLI, API) that needs to transform
a Word document into a DITA package. Provides a clean, stable API for
document conversion operations.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import slugify

# Core conversion operations
from orlando_toolkit.core.converter import (
    convert_docx_to_dita,
    save_dita_package,
    update_image_references_and_names,
    update_topic_references_and_names,
    prune_empty_topics,
)

logger = logging.getLogger(__name__)

__all__ = ["ConversionService"]


class ConversionService:
    """Business-logic façade with zero GUI / Tkinter dependencies."""

    def __init__(self) -> None:
        # Potential configuration injection point (not used yet)
        self.logger = logger

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------
    def convert(self, docx_path: str | Path, metadata: Dict[str, Any]) -> DitaContext:
        """Convert the Word document at *docx_path* to an in-memory DitaContext."""
        docx_path = str(docx_path)
        self.logger.info("Parsing document...")
        self.logger.debug("Converting DOCX -> DITA: %s", docx_path)
        context = convert_docx_to_dita(docx_path, dict(metadata))
        return context

    def prepare_package(self, context: DitaContext) -> DitaContext:
        """Apply final renaming of topics and images inside *context*."""
        self.logger.info("Preparing content for packaging...")
        depth_limit = int(context.metadata.get("topic_depth", 3))

        # ----------------------------------------------------------------
        # 1) Apply structure rules (merge + consolidate) via StructureService
        # ----------------------------------------------------------------
        from orlando_toolkit.core.services.structure_service import StructureService
        from orlando_toolkit.core.services.structure_models import StructureRules

        svc = StructureService()

        # Build excluded style map from metadata (level -> set[str])
        style_excl_map: dict[int, set[str]] = {}
        for key, val in context.metadata.get("exclude_style_map", {}).items():
            try:
                lvl = int(key)
                style_excl_map[lvl] = set(val)
            except ValueError:
                continue

        rules = StructureRules(
            max_depth=depth_limit,
            excluded_styles=style_excl_map,
            consolidate_sections=True,
        )

        context = svc.apply_rules(context, rules)

        # ---------------------------------------------------------------
        # 2) Prune now-empty topicrefs below depth_limit (structure only)
        # ---------------------------------------------------------------
        if context.ditamap_root is not None:
            from lxml import etree as _ET

            def _prune(node: _ET.Element, level: int = 1):
                for tref in list(node.findall("topicref")):
                    if level > depth_limit:
                        node.remove(tref)
                    else:
                        _prune(tref, level + 1)

            _prune(context.ditamap_root)

            # Remove unreferenced topics (already handled in merge, but safe)
            hrefs = {
                tref.get("href").split("/")[-1]
                for tref in context.ditamap_root.xpath(".//topicref[@href]")
            }
            context.topics = {fn: el for fn, el in context.topics.items() if fn in hrefs}

        # 3) Convert empty topics into structural headings
        context = prune_empty_topics(context)

        # 4) Rename items
        context = update_topic_references_and_names(context)
        context = update_image_references_and_names(context)

        # 5) Strip helper attributes (e.g., data-level) that are not valid DITA
        if context.ditamap_root is not None:
            for el in context.ditamap_root.xpath('.//*[@data-level or @data-style]'):
                el.attrib.pop('data-level', None)
                el.attrib.pop('data-style', None)
        return context

    def write_package(self, context: DitaContext, output_zip: str | Path, *,
                      debug_copy_dir: Optional[str | Path] = None) -> None:
        """Write *context* to *output_zip* (a ``.zip`` path).

        If *debug_copy_dir* is provided, the un-zipped folder is also copied
        there for inspection.
        """
        output_zip = Path(output_zip)
        self.logger.info("Writing ZIP package...")
        self.logger.debug("Destination: %s", output_zip)

        with tempfile.TemporaryDirectory(prefix="orlando_packager_") as tmp_dir:
            save_dita_package(context, tmp_dir)
            if debug_copy_dir:
                debug_dest = Path(debug_copy_dir)
                if debug_dest.exists():
                    shutil.rmtree(debug_dest)
                shutil.copytree(tmp_dir, debug_dest)
                self.logger.info("Debug copy written to %s", debug_dest)
            shutil.make_archive(output_zip.with_suffix(""), "zip", tmp_dir)

    # Convenience one-shot -------------------------------------------------
    def convert_and_package(
        self,
        docx_path: str | Path,
        metadata: Dict[str, Any],
        output_zip: str | Path,
        *,
        debug_copy_dir: Optional[str | Path] = None,
    ) -> Path:
        """Full pipeline: convert DOCX and immediately write a ZIP archive."""
        context = self.convert(docx_path, metadata)
        context = self.prepare_package(context)
        self.write_package(context, output_zip, debug_copy_dir=debug_copy_dir)
        return Path(output_zip)

    # ------------------------------------------------------------------
    # XML preview helper
    # ------------------------------------------------------------------

    def compile_preview(self, context: DitaContext, tref_element) -> str:  # noqa: D401
        """Return compiled XML string for *tref_element* inside *context*."""

        from orlando_toolkit.core.preview.xml_compiler import compile_topic_fragment

        return compile_topic_fragment(context, tref_element, pretty=True) 