from __future__ import annotations

"""Helper utilities for DOCX to DITA conversion.

Small, side-effect-free functions used by the core conversion logic
for XML element creation, formatting, and content processing.
"""

from datetime import datetime
import os
import re
from typing import Dict, Any, Optional, Tuple

from lxml import etree as ET  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX  # type: ignore
from docx.oxml.ns import qn  # type: ignore

from orlando_toolkit.core.utils import (
    slugify,
    generate_dita_id,
    convert_color_to_outputclass,
    normalize_topic_title,
)
from orlando_toolkit.config.manager import ConfigManager

__all__ = [
    "STYLE_MAP",
    "create_dita_concept",
    "add_orlando_topicmeta",
    "process_paragraph_content_and_images",
    "apply_paragraph_formatting",
    "get_heading_level",
]

# ---------------------------------------------------------------------------
# User-customisable style mapping (kept for backward compatibility)
# ---------------------------------------------------------------------------

STYLE_MAP: Dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Wingdings/Webdings symbol normalisation
# ---------------------------------------------------------------------------
# Word check-boxes are often inserted as Wingdings glyphs that live in the
# Private-Use Area (PUA).  Down-stream tool-chains rarely have a Wingdings font
# so the PUA code-points render as blank squares.  We map the handful of
# checkbox-related glyphs we care about to their public Unicode equivalents.

WINGDINGS_TO_UNICODE: Dict[str, str] = {
    # Unchecked box
    "\uf0a3": "☐",
    "\uf06f": "☐",  # Alternative from another font/version
    # Checked box
    "\uf0a4": "☑",
    "\uf078": "☑",  # Alternative checked box
    # Simple check mark
    "\uf0a8": "✓",
}

# ---------------------------------------------------------------------------
# DITA element builders
# ---------------------------------------------------------------------------

def create_dita_concept(title: str, topic_id: str, revision_date: str):
    """Return ``(<concept>, <conbody>)`` elements for a new DITA concept."""
    concept_root = ET.Element("concept", id=topic_id)
    title_elem = ET.SubElement(concept_root, "title")
    title_elem.text = normalize_topic_title(title)

    conbody = ET.SubElement(concept_root, "conbody")
    return concept_root, conbody


def add_orlando_topicmeta(map_root: ET.Element, metadata: Dict[str, Any]) -> None:
    """Insert the Orlando-specific ``<topicmeta>`` block into *map_root*."""
    topicmeta = ET.Element("topicmeta")
    critdates = ET.SubElement(topicmeta, "critdates")
    rev_date = metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d"))
    ET.SubElement(critdates, "created", date=rev_date)
    ET.SubElement(critdates, "revised", modified=rev_date)

    manual_code = metadata.get("manual_code") or slugify(metadata.get("manual_title", "default_code"))
    manual_ref = (
        metadata.get("manual_reference") or slugify(metadata.get("manual_title", "default_ref")).upper()
    )

    ET.SubElement(topicmeta, "othermeta", name="manualCode", content=manual_code)
    ET.SubElement(topicmeta, "othermeta", name="manual_reference", content=manual_ref)

    # Revision number handling: if the calling code specifies a revision_number we
    # embed it exactly.  Otherwise we explicitly mark it as null so downstream
    # systems (Orlando CMS) treat this package as an *edition* rather than an
    # *operator* (revision) release.
    rev_num = metadata.get("revision_number")
    if rev_num:
        ET.SubElement(topicmeta, "othermeta", name="revNumber", content=str(rev_num))
        ET.SubElement(topicmeta, "othermeta", name="isRevNumberNull", content="false")
    # When no revision_number is supplied we omit both revNumber and
    # isRevNumberNull so the CMS can apply its own default semantics (edition
    # upload).  Empirically this prevents the "operator release" error that
    # appears when the element is present with *content="true"*.

    title_element = map_root.find("title")
    insert_index = list(map_root).index(title_element) + 1 if title_element is not None else 0
    map_root.insert(insert_index, topicmeta)

# ---------------------------------------------------------------------------
# Paragraph processing helpers
# ---------------------------------------------------------------------------

def _get_all_paragraph_text_with_sdt(paragraph: Paragraph) -> str:
    """Get all text from a paragraph including SDT content, in document order."""
    try:
        from docx.oxml.ns import qn
        
        full_text = ""
        for child in paragraph._p:
            if child.tag == qn('w:r'):
                # Regular run
                for t_elem in child.iter():
                    if t_elem.tag == qn('w:t') and t_elem.text:
                        full_text += t_elem.text
            elif child.tag == qn('w:sdt'):
                # SDT element - extract and convert text
                sdt_text = ""
                for t_elem in child.iter():
                    if t_elem.tag == qn('w:t') and t_elem.text:
                        sdt_text += t_elem.text
                if sdt_text:
                    converted_text = "".join(WINGDINGS_TO_UNICODE.get(ch, ch) for ch in sdt_text)
                    full_text += converted_text
        
        return full_text
    except Exception:
        return paragraph.text  # Fallback to regular text

def _split_mixed_table_content(paragraph: Paragraph) -> list[str]:
    """Split paragraph content with mixed text and checkboxes into logical parts for table cells."""
    try:
        from docx.oxml.ns import qn
        
        parts = []
        current_part = ""
        
        for child in paragraph._p:
            if child.tag == qn('w:r'):
                # Regular run - add to current part
                for t_elem in child.iter():
                    if t_elem.tag == qn('w:t') and t_elem.text:
                        current_part += t_elem.text
            elif child.tag == qn('w:sdt'):
                # SDT element (checkbox) - finish current part and start new one
                if current_part.strip():
                    parts.append(current_part.strip())
                    current_part = ""
                
                # Extract checkbox and add as separate part
                sdt_text = ""
                for t_elem in child.iter():
                    if t_elem.tag == qn('w:t') and t_elem.text:
                        sdt_text += t_elem.text
                if sdt_text:
                    converted_text = "".join(WINGDINGS_TO_UNICODE.get(ch, ch) for ch in sdt_text)
                    if converted_text.strip():
                        parts.append(converted_text.strip())
        
        # Add any remaining text
        if current_part.strip():
            parts.append(current_part.strip())
        
        # If no parts found, fall back to regular text
        if not parts:
            text = paragraph.text.strip()
            if text:
                parts.append(text)
        
        return parts
    except Exception:
        # Fallback to single part
        text = paragraph.text.strip()
        return [text] if text else []

def _process_paragraph_runs(p_element: ET.Element, paragraph: Paragraph, image_map: dict, *, exclude_images: bool = False) -> None:  # noqa: D401,E501
    """Rebuild the runs of a Word paragraph into DITA inline markup."""
    # Check if this paragraph has SDT content that regular runs miss
    regular_text = paragraph.text or ""
    sdt_aware_text = _get_all_paragraph_text_with_sdt(paragraph)
    
    # If SDT extraction found additional content, use simple text approach
    if sdt_aware_text != regular_text and sdt_aware_text.strip():
        p_element.text = sdt_aware_text
        return
    
    last_element: Optional[ET.Element] = None

    # python-docx ≥0.9.8 exposes iter_inner_content()
    try:
        content_items = list(paragraph.iter_inner_content())  # type: ignore[attr-defined]
    except AttributeError:
        # Special case: if the paragraph has no runs but has text, create a simple text node
        if not paragraph.runs and paragraph.text:
            simple_text = _get_all_paragraph_text_with_sdt(paragraph)
            if simple_text.strip():
                p_element.text = simple_text
            return

        # If paragraph has no actual content, skip it
        paragraph_text = _get_all_paragraph_text_with_sdt(paragraph)
        if not paragraph.runs and not paragraph_text:
            return
        
        # Fallback: collect runs including those inside SDT wrappers
        content_items = []
        for run in paragraph.runs:
            content_items.append(run)

    current_group: list[str] = []
    current_formatting: Optional[Tuple[Tuple[str, ...], Optional[str]]] = None

    color_rules = ConfigManager().get_color_rules()

    def finish_current_group() -> None:
        nonlocal current_group, current_formatting, last_element
        if not current_group:
            return
        consolidated_text = "".join(current_group)
        formatting_tuple: Tuple[str, ...] = current_formatting[0] if current_formatting else tuple()
        run_color: Optional[str] = current_formatting[1] if current_formatting else None

        if formatting_tuple or run_color:
            target_element: Optional[ET.Element] = None
            innermost_element: Optional[ET.Element] = None

            # Base <ph> for colour
            if run_color:
                target_element = ET.Element("ph", id=generate_dita_id())
                target_element.set("class", "- topic/ph ")
                color_class = convert_color_to_outputclass(run_color, color_rules)
                if color_class:
                    target_element.set("outputclass", color_class)
                innermost_element = target_element

            def _nest(tag: str) -> ET.Element:
                nonlocal target_element, innermost_element
                el = ET.Element(tag, id=generate_dita_id())
                el.set("class", f"+ topic/ph hi-d/{tag} ")
                if innermost_element is not None:
                    innermost_element.append(el)
                else:
                    target_element = el
                innermost_element = el
                return el

            if "bold" in formatting_tuple:
                _nest("b")
            if "italic" in formatting_tuple:
                _nest("i")
            if "underline" in formatting_tuple:
                _nest("u")
            if "superscript" in formatting_tuple:
                _nest("sup")

            if innermost_element is not None:
                innermost_element.text = consolidated_text
                p_element.append(target_element)  # type: ignore[arg-type]
                last_element = target_element
        else:
            if last_element is not None:
                last_element.tail = (last_element.tail or "") + consolidated_text
            else:
                p_element.text = (p_element.text or "") + consolidated_text  # type: ignore[assignment]

        current_group = []
        current_formatting = None

    for item in content_items:
        # Hyperlink handling
        if hasattr(item, "address"):
            finish_current_group()
            href_el = ET.Element("xref", id=generate_dita_id())
            href_el.set("class", "- topic/xref ")
            href_el.set("format", "html")
            href_el.set("scope", "external")
            href_el.set("href", item.url or item.address)  # type: ignore[attr-defined]
            href_el.text = item.text  # type: ignore[attr-defined]
            p_element.append(href_el)
            last_element = href_el
            continue

        run = item  # regular run -------------------------------------------
        # ------------------------------------------------------------------
        # Replace Wingdings PUA checkbox glyphs with their proper Unicode.
        # We do not rely on `run.font.name` because some Word files lose the
        # Wingdings font information during editing or template merging.
        # ------------------------------------------------------------------
        run_raw = run.text or ""
        run_text = "".join(WINGDINGS_TO_UNICODE.get(ch, ch) for ch in run_raw)
        run_format = []
        if run.bold:
            run_format.append("bold")
        if run.italic:
            run_format.append("italic")
        if run.underline:
            run_format.append("underline")
        
        # New check for superscript via direct XML property
        vert_align = run.element.xpath("./w:rPr/w:vertAlign/@w:val")
        if run.font.superscript or (vert_align and vert_align[0] == "superscript"):
            run_format.append("superscript")

        # colour extraction (simplified)
        run_color: Optional[str] = None
        try:
            font_color = run.font.color  # type: ignore[attr-defined]
            if font_color:
                # 1) explicit RGB ------------------------------------------------
                if font_color.rgb:
                    run_color = f"#{str(font_color.rgb).lower()}"
                # 2) theme (no tint/shade) -------------------------------------
                elif getattr(font_color, "theme_color", None) and not (getattr(font_color, "tint", None) or getattr(font_color, "shade", None)):
                    theme_name = font_color.theme_color.name.lower()  # type: ignore[attr-defined]
                    run_color = f"theme-{theme_name}"
                # 3) theme + tint/shade ----------------------------------------
                elif getattr(font_color, "theme_color", None):
                    theme_name = font_color.theme_color.name.lower()  # type: ignore[attr-defined]
                    base_hex = color_rules.get("theme_rgb", {}).get(theme_name)
                    if base_hex:
                        tint = getattr(font_color, "tint", 0) or 0  # lighten (0..1)
                        shade = getattr(font_color, "shade", 0) or 0  # darken (0..1)

                        def _lerp(c: int, target: int, factor: float) -> int:
                            return int(round(c + (target - c) * factor))

                        r = int(base_hex[1:3], 16)
                        g = int(base_hex[3:5], 16)
                        b = int(base_hex[5:7], 16)
                        if tint:
                            r, g, b = (_lerp(v, 255, tint) for v in (r, g, b))
                        elif shade:
                            r, g, b = (_lerp(v, 0, shade) for v in (r, g, b))
                        run_color = f"#{r:02x}{g:02x}{b:02x}"
            # 4) highlight (background) ----------------------------------------
            hl = run.font.highlight_color  # type: ignore[attr-defined]
            if not run_color and hl is not None and hl != WD_COLOR_INDEX.AUTO:
                run_color = f"background-{hl.name.lower()}"
        except Exception:
            pass

        fmt_tuple: Tuple[Tuple[str, ...], Optional[str]] = (tuple(run_format), run_color)
        if current_formatting == fmt_tuple:
            current_group.append(run_text)
        else:
            finish_current_group()
            current_group = [run_text]
            current_formatting = fmt_tuple

        # image handling ------------------------------------------------------
        if not exclude_images:
            r_ids = run.element.xpath(".//@r:embed")
            if r_ids and r_ids[0] in image_map:
                img_filename = os.path.basename(image_map[r_ids[0]])
                ET.SubElement(p_element, "image", href=f"../media/{img_filename}", id=generate_dita_id())

    finish_current_group()


def process_paragraph_content_and_images(
    p_element: ET.Element,
    paragraph: Paragraph,
    image_map: dict,
    conbody: Optional[ET.Element],
) -> None:
    """Split images into separate centred paragraphs when *conbody* is provided."""

    if conbody is None:
        _process_paragraph_runs(p_element, paragraph, image_map, exclude_images=False)
        return

    images: list[str] = []
    for run in paragraph.runs:
        r_ids = run.element.xpath(".//@r:embed")
        if r_ids and r_ids[0] in image_map:
            images.append(os.path.basename(image_map[r_ids[0]]))

    _process_paragraph_runs(p_element, paragraph, image_map, exclude_images=True)

    for img in images:
        img_p = ET.SubElement(conbody, "p", id=generate_dita_id(), outputclass="align-center")
        ET.SubElement(img_p, "image", href=f"../media/{img}", id=generate_dita_id())


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def apply_paragraph_formatting(p_element: ET.Element, paragraph: Paragraph) -> None:
    """Set ``outputclass`` on *p_element* to reflect paragraph alignment/shading."""
    classes: list[str] = []
    if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER:  # type: ignore[attr-defined]
        classes.append("align-center")
    elif paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:  # type: ignore[attr-defined]
        classes.append("align-justify")

    p_pr = paragraph._p.pPr  # type: ignore[attr-defined]
    if p_pr is not None:
        shd = p_pr.find(qn("w:shd"))
        if shd is not None and shd.attrib.get(qn("w:fill")) == "F2F2F2":
            classes.append("roundedbox")

    if classes:
        p_element.set("outputclass", " ".join(classes))

# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

def get_heading_level(paragraph: Paragraph, style_map: Optional[dict] = None) -> Optional[int]:
    """Return heading level for *paragraph*, or ``None`` if it is not a heading."""
    try:
        # 1) Explicit user mapping
        if paragraph.style and paragraph.style.name:  # type: ignore[attr-defined]
            style_name = paragraph.style.name
            if style_map and style_name in style_map:
                return int(style_map[style_name])
            if style_name.startswith("Heading ") and style_name.split(" ")[-1].isdigit():
                return int(style_name.split(" ")[-1])

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        outline_vals = paragraph._p.xpath("./w:pPr/w:outlineLvl/@w:val", namespaces=ns)
        if outline_vals:
            return int(outline_vals[0]) + 1

        if paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
            numPr = paragraph._p.pPr.numPr
            ilvl = getattr(numPr.ilvl, "val", None)
            if ilvl is not None:
                try:
                    return int(ilvl) + 1
                except ValueError:
                    pass
    except Exception:
        pass

    return None 