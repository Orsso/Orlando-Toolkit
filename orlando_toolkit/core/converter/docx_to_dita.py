from __future__ import annotations

"""DOCX → DITA conversion implementation.

Core conversion logic that transforms Word documents into DITA topics
and ditamaps with proper Orlando-specific metadata and structure.
"""

from datetime import datetime
import logging
import re
from typing import Any, Dict

from docx import Document  # type: ignore

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.parser import extract_images_to_context, build_style_heading_map

# Helper functions migrated from legacy converter
from .helpers import (
    STYLE_MAP,
    add_orlando_topicmeta,
)

logger = logging.getLogger(__name__)

__all__ = ["convert_docx_to_dita"]


def convert_docx_to_dita(file_path: str, metadata: Dict[str, Any]) -> DitaContext:  # noqa: C901 (complex)
    """Convert a DOCX file into an in-memory DitaContext.

    Processes Word document structure, formatting, images, and metadata
    to generate Orlando-compliant DITA topics and ditamap.
    """
    logger.info("Starting DOCX->DITA conversion (core.converter)...: %s", file_path)

    context = DitaContext(metadata=dict(metadata))

    try:
        logger.info("Loading DOCX file...")
        doc = Document(file_path)
        all_images_map_rid = extract_images_to_context(doc, context)

        logger.info("Extracting images...")

        map_root = ET.Element("map")
        map_root.set("{http://www.w3.org/XML/1998/namespace}lang", "en-US")
        context.ditamap_root = map_root

        map_title = ET.SubElement(map_root, "title")
        map_title.text = metadata.get("manual_title", "Document Title")

        add_orlando_topicmeta(map_root, context.metadata)

        style_heading_map = build_style_heading_map(doc)
        style_heading_map.update(STYLE_MAP)

        # Optional user override mapping provided via metadata
        if isinstance(metadata.get("style_heading_map"), dict):
            style_heading_map.update(metadata["style_heading_map"])  # type: ignore[arg-type]

        # Generic heading-name detection (e.g., "HEADING 5 GM"). Enabled by
        # default but can be disabled with metadata["generic_heading_match"] = False.
        if metadata.get("generic_heading_match", True):
            heading_rx = re.compile(r"\b(?:heading|titre)[ _]?(\\d)\\b", re.IGNORECASE)
            for sty in doc.styles:  # type: ignore[attr-defined]
                try:
                    name = sty.name  # type: ignore[attr-defined]
                except Exception:
                    continue
                m = heading_rx.search(name or "")
                if m and name not in style_heading_map:
                    try:
                        lvl = int(m.group(1))
                        style_heading_map[name] = lvl
                    except ValueError:
                        pass

        logger.info("Building topics...")
        
        # ======================================================================
        # NEW TWO-PASS APPROACH: Build structure first, then generate DITA
        # ======================================================================
        from orlando_toolkit.core.converter.structure_builder import (
            build_document_structure,
            determine_node_roles,
            generate_dita_from_structure
        )
        
        # Pass 1: Build complete document structure
        logger.info("Analyzing document structure...")
        root_nodes = build_document_structure(doc, style_heading_map, all_images_map_rid)
        
        # Pass 2: Determine section vs module roles
        logger.info("Determining section/module roles...")
        determine_node_roles(root_nodes)
        
        # Pass 3: Generate DITA topics and map structure
        logger.info("Generating DITA topics...")
        heading_counters = [0] * 9
        parent_elements: Dict[int, ET.Element] = {0: map_root}
        
        generate_dita_from_structure(
            root_nodes, 
            context, 
            context.metadata,
            all_images_map_rid,
            map_root,
            heading_counters,
            parent_elements
        )

        # ------------------------------------------------------------------
        # Post-processing: collapse singleton sections (section with single
        # BodyContent module) to avoid redundant nesting like "DIFFUSION →
        # DIFFUSION" that confuses the GUI and merge logic.
        # ------------------------------------------------------------------
        try:
            from orlando_toolkit.core.merge import _collapse_singleton_sections  # local import to avoid circular deps
            _collapse_singleton_sections(context.ditamap_root)
        except Exception as exc:  # pragma: no cover – defensive logging only
            logger.warning("Post-conversion singleton collapse failed: %s", exc)

    except Exception as exc:
        logger.error("Conversion failed: %s", exc, exc_info=True)
        raise

    logger.info("Conversion finished.")
    return context 