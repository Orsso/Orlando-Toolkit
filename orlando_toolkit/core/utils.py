from __future__ import annotations

"""Simple reusable helper functions.

These helpers are side-effect-free and contain no GUI or disk I/O; they can be
used across all layers of the toolkit.
"""

from typing import Any, Optional, Dict
import re
import uuid
from lxml import etree as ET
import xml.dom.minidom as _minidom

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext

__all__ = [
    "slugify",
    "generate_dita_id",
    "normalize_topic_title",
    "save_xml_file",
    "save_minified_xml_file",
    "convert_color_to_outputclass",
    "calculate_section_numbers",
    "get_section_number_for_topicref",
    "find_topicref_for_image",
]


def slugify(text: str) -> str:
    """Return a file-system-safe slug version of *text*.

    Removes non-alphanumeric chars, converts whitespace/dashes to underscores,
    and lower-cases the result. Mirrors previous implementation from
    ``docx_to_dita_converter`` for backward compatibility.
    """
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


def generate_dita_id() -> str:
    """Generate a globally unique ID suitable for DITA elements."""
    return f"id-{uuid.uuid4()}"


def normalize_topic_title(title: str) -> str:
    """Normalize topic titles to uppercase as per Orlando requirements.
    
    This function converts topic titles to uppercase to ensure consistent
    formatting across all topic types including topichead and merged sub topics.
    
    Parameters
    ----------
    title
        The original title text
        
    Returns
    -------
    str
        The title converted to uppercase, with whitespace preserved
    """
    if not title:
        return title
    return title.upper()


# ---------------------------------------------------------------------------
# XML convenience wrappers
# ---------------------------------------------------------------------------

# We keep exact behaviour of legacy functions to guarantee no regression.


def save_xml_file(element: ET.Element, path: str, doctype_str: str, *, pretty: bool = True) -> None:
    """Write *element* to *path* with XML declaration and supplied doctype.

    Parameters
    ----------
    element
        Root ``lxml`` element to serialise.
    path
        Destination file path (will be opened in binary mode).
    doctype_str
        Full doctype string, including leading whitespace; e.g.::

            '\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
    pretty
        When *True* (default) lxml pretty-prints the output; matches previous
        behaviour in :pyfile:`src/docx_to_dita_converter.py`.
    """

    xml_bytes = ET.tostring(
        element,
        pretty_print=pretty,
        xml_declaration=True,
        encoding="UTF-8",
        doctype=doctype_str,
    )
    with open(path, "wb") as fh:
        fh.write(xml_bytes)


def save_minified_xml_file(element: ET.Element, path: str, doctype_str: str) -> None:
    """Save *element* on a single line (minified) to *path*.

    This reproduces the logic previously embedded in the converter.
    """

    xml_bytes = ET.tostring(element, encoding="UTF-8")
    dom = _minidom.parseString(xml_bytes)
    minified_content = dom.documentElement.toxml() if dom.documentElement else ""

    full = f'<?xml version="1.0" encoding="UTF-8"?>{doctype_str}{minified_content}'
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(full)


# ---------------------------------------------------------------------------
# Colour mapping utilities (extracted from original converter)  [p3c]
# ---------------------------------------------------------------------------

def convert_color_to_outputclass(
    color_value: Optional[str], color_rules: Dict[str, Any]
) -> Optional[str]:
    """Map Word colour representation to Orlando `outputclass` (red/green).

    The logic is unchanged from the legacy implementation, supporting:
    • exact hex matches (case-insensitive)
    • a limited set of Word theme colours
    • heuristic detection based on RGB dominance.
    """
    if not color_value:
        return None

    color_mappings = color_rules.get("color_mappings", {})
    theme_map = color_rules.get("theme_map", {})

    color_lower = color_value.lower()
    if color_lower in color_mappings:
        return color_mappings[color_lower]

    if color_value.startswith("theme-"):
        theme_name = color_value[6:]
        return theme_map.get(theme_name)

    # Background colour tokens coming from shading (already prefixed)
    if color_value.startswith("background-"):
        return color_mappings.get(color_value)

    # ------------------------------------------------------------------
    # HSV-based tolerance fallback (optional)
    # ------------------------------------------------------------------
    tolerance_cfg = color_rules.get("tolerance", {})
    if color_lower.startswith("#") and len(color_lower) == 7 and tolerance_cfg:
        try:
            r = int(color_lower[1:3], 16) / 255.0
            g = int(color_lower[3:5], 16) / 255.0
            b = int(color_lower[5:7], 16) / 255.0

            import colorsys

            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            h_deg = h * 360
            s_pct = s * 100
            v_pct = v * 100

            for out_class, spec in tolerance_cfg.items():
                # Extract ranges
                hue_range = spec.get("hue")
                hue2_range = spec.get("hue2")  # optional secondary segment (wrap-around)
                sat_min = spec.get("sat_min", 0)
                val_min = spec.get("val_min", 0)

                def _in_range(hrange: list[int] | tuple[int, int] | None) -> bool:
                    if not hrange:
                        return False
                    start, end = hrange
                    return start <= h_deg <= end

                if (
                    (_in_range(hue_range) or _in_range(hue2_range))
                    and s_pct >= sat_min
                    and v_pct >= val_min
                ):
                    return out_class
        except Exception:
            pass

    return None 

# ---------------------------------------------------------------------------
# Section numbering utilities
# ---------------------------------------------------------------------------

def calculate_section_numbers(ditamap_root: ET.Element) -> Dict[ET.Element, str]:
    """Calculate hierarchical section numbers for all topicref/topichead elements.
    
    Parameters
    ----------
    ditamap_root
        Root element of the ditamap
        
    Returns
    -------
    Dict[ET.Element, str]
        Mapping from topicref/topichead elements to their section numbers (e.g., "1.2.1")
    """
    section_map = {}
    
    def _walk_elements(parent_element: ET.Element, counters: list[int]):
        """Recursively walk the element tree and assign section numbers."""
        current_level = len(counters)
        child_counter = 0
        
        for element in parent_element:
            if element.tag in ("topicref", "topichead"):
                child_counter += 1
                
                # Extend counters if needed for this level
                level_counters = counters.copy() + [child_counter]
                
                # Generate section number string
                section_number = ".".join(str(c) for c in level_counters)
                section_map[element] = section_number
                
                # Recursively process children
                _walk_elements(element, level_counters)
    
    # Start with empty counters for root level
    _walk_elements(ditamap_root, [])
    return section_map


def get_section_number_for_topicref(topicref: ET.Element, ditamap_root: ET.Element) -> str:
    """Get the section number for a specific topicref element.
    
    Parameters
    ----------
    topicref
        The topicref element to get the section number for
    ditamap_root
        Root element of the ditamap
        
    Returns
    -------
    str
        Section number (e.g., "1.2.1") or "0" if not found
    """
    section_map = calculate_section_numbers(ditamap_root)
    return section_map.get(topicref, "0")


def find_topicref_for_image(image_filename: str, context: "DitaContext") -> Optional[ET.Element]:
    """Find the topicref element that contains a specific image.
    
    Parameters
    ----------
    image_filename
        The filename of the image to search for
    context
        The DITA context containing topics and ditamap
        
    Returns
    -------
    Optional[ET.Element]
        The topicref element containing the image, or None if not found
    """
    if not context.ditamap_root:
        return None
    
    # Search through all topics to find which one contains the image
    for topic_filename, topic_element in context.topics.items():
        # Look for image references in the topic
        image_elements = topic_element.xpath(f".//image[@href='../media/{image_filename}']")
        if image_elements:
            # Find the corresponding topicref in the ditamap
            for topicref in context.ditamap_root.xpath(".//topicref"):
                href = topicref.get("href", "")
                if href.endswith(topic_filename):
                    return topicref
    
    return None 