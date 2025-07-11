from __future__ import annotations

"""Topic merge helper – joins content from descendants deeper than a depth limit.

This module is UI-agnostic and manipulates only the in-memory DitaContext.
It must not perform any file I/O so that it can be reused by CLI, GUI and tests.
"""

from copy import deepcopy
from typing import Set
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext  # noqa: F401
from orlando_toolkit.core.utils import generate_dita_id

__all__ = [
    "merge_topics_by_titles", 
    "merge_topics_unified",
]


BLOCK_LEVEL_TAGS: Set[str] = {
    "p",
    "ul",
    "ol",
    "sl",
    "table",
    "section",
    "fig",
    "image",
    "codeblock",
}


def _copy_content(src_topic: ET.Element, dest_topic: ET.Element) -> None:
    """Append block-level children from *src_topic* into *dest_topic*."""

    dest_body = dest_topic.find("conbody")
    if dest_body is None:
        dest_body = ET.SubElement(dest_topic, "conbody")

    src_body = src_topic.find("conbody")
    if src_body is None:
        return

    for child in list(src_body):
        if child.tag in BLOCK_LEVEL_TAGS:
            # Shallow copy so we don't affect original
            new_child = deepcopy(child)
            # Ensure unique @id attributes to avoid duplicates
            id_map = {}
            if "id" in new_child.attrib:
                old = new_child.get("id")
                new = generate_dita_id()
                new_child.set("id", new)
                id_map[old] = new

            # Also dedup nested IDs and collect mapping
            for el in new_child.xpath('.//*[@id]'):
                old = el.get("id")
                new = generate_dita_id()
                el.set("id", new)
                id_map[old] = new

            # Update internal references within the copied subtree
            for el in new_child.xpath('.//*[@href|@conref]'):
                for attr in ("href", "conref"):
                    val = el.get(attr)
                    if val and val.startswith("#"):
                        ref = val[1:]
                        if ref in id_map:
                            el.set(attr, f"#{id_map[ref]}")
            dest_body.append(new_child)



def _clean_title(raw: str | None) -> str:
    """Normalize *raw* heading text for reliable comparisons."""
    if not raw:
        return ""
    return " ".join(raw.split()).lower()


def merge_topics_by_titles(ctx: "DitaContext", exclude_titles: set[str]) -> None:
    """Merge any topics whose *title* is in *exclude_titles* into their parent.

    The comparison is case-insensitive and whitespace-insensitive. This operates on an explicit
    list of forbidden titles, independent of depth.
    """

    if not exclude_titles or ctx.ditamap_root is None:
        return

    # Pre-normalize for O(1) look-ups
    targets = {_clean_title(t) for t in exclude_titles}

    removed: Set[str] = set()

    def _walk(parent_ref, ancestor_topic_el):
        for tref in list(parent_ref):
            if tref.tag not in ("topicref", "topichead"):
                continue

            href = tref.get("href")
            topic_el = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            # Title to test comes from navtitle (preferred) or topic title
            title_txt = ""
            navtitle_el = tref.find("topicmeta/navtitle")
            if navtitle_el is not None and navtitle_el.text:
                title_txt = navtitle_el.text
            elif topic_el is not None:
                t_el = topic_el.find("title")
                title_txt = t_el.text if t_el is not None else ""

            if _clean_title(title_txt) in targets and ancestor_topic_el is not None and topic_el is not None:
                # 1) Preserve heading paragraph
                head_p = ET.Element("p", id=generate_dita_id())
                head_p.text = title_txt.strip()

                parent_body = ancestor_topic_el.find("conbody")
                if parent_body is None:
                    parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                parent_body.append(head_p)

                # 2) Merge body content
                _copy_content(topic_el, ancestor_topic_el)

                # 3) Recurse into descendants so grand-children also merge
                _walk(tref, ancestor_topic_el)

                # 4) Remove topicref & mark topic for purge
                parent_ref.remove(tref)
                if fname:
                    removed.add(fname)
            else:
                # Continue traversal; update ancestor when we have a real topic
                next_ancestor = topic_el if topic_el is not None else ancestor_topic_el
                _walk(tref, next_ancestor)

    _walk(ctx.ditamap_root, None)

    for fname in removed:
        ctx.topics.pop(fname, None)

    # Mark to avoid duplicate processing
    ctx.metadata["merged_exclude"] = True





# ---------------------------------------------------------------------------
# Helper utilities (internal)
# ---------------------------------------------------------------------------


def _new_topic_with_title(title_text: str) -> ET.Element:
    """Create a bare <concept> topic element with *title_text*."""
    topic_el = ET.Element("concept", id=generate_dita_id())
    title_el = ET.SubElement(topic_el, "title")
    title_el.text = title_text
    # Body will be added later when content is copied
    return topic_el


def _ensure_content_module(ctx: "DitaContext", section_tref: ET.Element) -> ET.Element:
    """Ensure there is a child *module* topic under *section_tref* and return its <concept> element.

    If the first child already references a topic (module) we reuse it, otherwise we
    create a new topic file, register it in ctx.topics and insert a new <topicref>.
    """
    
    # For merge operations, always create a fresh content module
    # Don't reuse existing topics that are meant to be merged
    
    # Create a fresh content module
    # Derive filename similar to converter naming scheme: topic_<id>.dita
    new_id = generate_dita_id()
    fname = f"topic_{new_id}.dita"

    # Build topic element
    section_title_el = section_tref.find("topicmeta/navtitle")
    title_txt = section_title_el.text if section_title_el is not None and section_title_el.text else "Untitled"
    topic_el = _new_topic_with_title(title_txt)

    # Register in topics map
    ctx.topics[fname] = topic_el

    # Create child topicref
    child_ref = ET.Element("topicref", href=f"topics/{fname}")
    # Content modules should have the same level as their parent section to avoid being merged
    module_level = str(int(section_tref.get("data-level", 1)))
    child_ref.set("data-level", module_level)
    # Keep navtitle in sync
    nav = ET.SubElement(child_ref, "topicmeta")
    navtitle = ET.SubElement(nav, "navtitle")
    navtitle.text = title_txt

    # Insert as first child to preserve order
    section_tref.insert(0, child_ref)

    return topic_el 


def merge_topics_unified(ctx: "DitaContext", depth_limit: int, exclude_style_map: dict[int, set[str]] = None) -> None:
    """Unified merge that handles both depth limits and style exclusions in a single pass.
    
    This replaces the problematic sequential approach that caused content loss.
    Merges topics if they exceed depth_limit OR if their (level, style) is in exclude_style_map.
    
    Parameters
    ----------
    ctx : DitaContext
        The context containing topics and ditamap to modify
    depth_limit : int
        Maximum allowed depth (topics deeper than this get merged)
    exclude_style_map : dict[int, set[str]], optional
        Map of level -> set of style names to exclude/merge
    """
    
    if ctx.ditamap_root is None:
        return
        
    exclude_style_map = exclude_style_map or {}
    removed_topics: Set[str] = set()
    
    # Track content modules created for each topichead to avoid duplicates
    topichead_modules: dict[ET.Element, ET.Element] = {}
    
    def _should_merge(tref: ET.Element) -> bool:
        """Determine if a topicref should be merged based on depth OR style."""
        # topichead elements are never merged (pure structure)
        if tref.tag == "topichead":
            return False
            
        t_level = int(tref.get("data-level", 1))  # Use actual data-level attribute
        style_name = tref.get("data-style", "")
        
        # Merge if beyond depth limit
        if t_level > depth_limit:
            return True
            
        # Merge if style is excluded for this level
        if t_level in exclude_style_map and style_name in exclude_style_map[t_level]:
            return True
            
        return False
    
    def _recurse(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None, ancestor_tref: ET.Element | None = None):
        """Single-pass traversal that applies both depth and style criteria."""
        
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))

            # Resolve the topic element that this topicref points to (if any)
            href = tref.get("href")
            topic_el: ET.Element | None = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            # Check if this topic should be merged (unified decision)
            if _should_merge(tref):
                if fname and fname.startswith("topic_") and "." in fname:
                    # Check if this is a UUID-based content module (topic_<uuid>.dita)
                    base_name = fname.replace(".dita", "")
                    if len(base_name.split("_")) == 2 and len(base_name.split("_")[1]) == 10:
                        pass # Removed debug print
                if ancestor_topic_el is not None and topic_el is not None:
                    # Merge: preserve title and copy content to ancestor
                    title_el = topic_el.find("title")
                    if title_el is not None and title_el.text:
                        clean_title = " ".join(title_el.text.split())
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = clean_title

                        parent_body = ancestor_topic_el.find("conbody")
                        if parent_body is None:
                            parent_body = ET.SubElement(ancestor_topic_el, "conbody")
                        parent_body.append(head_p)

                    _copy_content(topic_el, ancestor_topic_el)

                    # Recurse into children, still targeting same ancestor
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)

                    # Remove merged topicref and mark topic for deletion
                    node.remove(tref)
                    removed_topics.add(fname)
                    
                elif ancestor_topic_el is None and topic_el is not None:
                    # No ancestor yet but we have content - need to find/create one
                    # Look for a content module in the parent structure
                    parent_module = None
                    solo_child_promoted = False
                    # Start with the immediate parent of this topicref, not the container
                    current = tref.getparent()
                    
                    while current is not None and parent_module is None and not solo_child_promoted:
                        if current.tag == "topichead":
                            # Check if we already created a content module for this topichead
                            if current in topichead_modules:
                                parent_module = topichead_modules[current]
                            else:
                                # Check if this is a solo child section that can be optimized
                                section_children = [child for child in current if child.tag == "topicref" and child.get("href")]
                                
                                if len(section_children) == 1 and section_children[0] is tref:
                                    # Solo child optimization: this is the only child in the section
                                    # Instead of creating a content module, promote this child to replace the section
                                    
                                    # Update the child's title to match the section
                                    section_title_el = current.find("topicmeta/navtitle")
                                    if section_title_el is not None and section_title_el.text:
                                        # Update topic title
                                        if topic_el is not None:
                                            topic_title_el = topic_el.find("title")
                                            if topic_title_el is not None:
                                                topic_title_el.text = section_title_el.text
                                        
                                        # Update topicref navtitle
                                        child_navtitle = tref.find("topicmeta/navtitle")
                                        if child_navtitle is not None:
                                            child_navtitle.text = section_title_el.text
                                    
                                    # Copy section attributes to the child
                                    for attr, value in current.attrib.items():
                                        if attr not in ("data-level",):  # Preserve child's level
                                            tref.set(attr, value)
                                    
                                    # Replace section with the promoted child in the parent
                                    section_parent = current.getparent()
                                    if section_parent is not None:
                                        section_index = list(section_parent).index(current)
                                        section_parent.remove(current)
                                        section_parent.insert(section_index, tref)
                                    
                                    # Mark that we've done a solo child promotion
                                    solo_child_promoted = True
                                    break
                                else:
                                    # Multiple children or different child: create a content module for this topichead
                                    parent_module = _ensure_content_module(ctx, current)
                                    topichead_modules[current] = parent_module
                            
                            # Found/created module, stop looking
                            break
                        elif current.tag == "topicref" and current.get("href"):
                            # Found a content-bearing topicref
                            parent_fname = current.get("href").split("/")[-1]
                            parent_module = ctx.topics.get(parent_fname)
                            if parent_module is not None:
                                break
                        current = current.getparent()
                    
                    # If we promoted a solo child, skip the rest of the merge logic
                    if solo_child_promoted:
                        continue
                    
                    if parent_module is not None:
                        # Copy title and content to the module
                        title_el = topic_el.find("title")
                        if title_el is not None and title_el.text:
                            clean_title = " ".join(title_el.text.split())
                            head_p = ET.Element("p", id=generate_dita_id())
                            head_p.text = clean_title
                            tb = parent_module.find("conbody")
                            if tb is None:
                                tb = ET.SubElement(parent_module, "conbody")
                            tb.append(head_p)

                        _copy_content(topic_el, parent_module)

                        # Recurse deeper merging into the parent_module
                        _recurse(tref, t_level + 1, parent_module, tref)

                        # Remove source tref and mark for deletion
                        node.remove(tref)
                        removed_topics.add(fname)
                        continue
                    else:
                        # Default: traverse deeper without removing (pass current ancestor)
                        _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
                else:
                    # No ancestor or no topic - just traverse deeper
                    _recurse(tref, t_level + 1, ancestor_topic_el, ancestor_tref)
            else:
                # Not merging - traverse deeper with updated ancestor
                # Only update ancestor if this is a topicref with content (has href)
                if tref.tag == "topicref" and href and topic_el is not None:
                    # This topicref can hold content, so it becomes the new ancestor
                    next_ancestor_topic = topic_el
                    next_ancestor_tref = tref
                else:
                    # topichead or no topic, keep current ancestor
                    next_ancestor_topic = ancestor_topic_el
                    next_ancestor_tref = ancestor_tref
                    
                _recurse(tref, t_level + 1, next_ancestor_topic, next_ancestor_tref)

    # Start the unified traversal
    _recurse(ctx.ditamap_root, 1, None, None)

    # Clean up merged topics
    for fname in removed_topics:
        ctx.topics.pop(fname, None)

    # Post-merge cleanup: collapse redundant section + content module structures
    _collapse_redundant_sections(ctx)
    
    # Additional step: handle remaining sections (run until no more changes)
    _optimize_remaining_sections(ctx, depth_limit)

    # Final cleanup: remove any orphaned topics that are no longer referenced
    _final_cleanup_orphaned_topics(ctx)

    # Set metadata to indicate both operations completed
    ctx.metadata["merged_depth"] = depth_limit
    if exclude_style_map:
        ctx.metadata["merged_exclude_styles"] = True


def _collapse_redundant_sections(ctx: "DitaContext") -> None:
    """Collapse topichead sections that have only a content module left.
    
    When filtering removes all children except the content module, the section/module
    separation becomes redundant. This function merges them into a single topic.
    """
    if ctx.ditamap_root is None:
        return
    
    def _find_collapsible_sections(node: ET.Element) -> list[ET.Element]:
        """Find topichead sections that only have one content module child."""
        collapsible = []
        
        for topichead in node.findall(".//topichead"):
            # Count actual topicref children (not metadata)
            children = [child for child in topichead if child.tag in ("topicref", "topichead")]
            
            # Section is collapsible if it has exactly one child with content
            if len(children) == 1:
                child = children[0]
                child_href = child.get("href")
                if child_href:
                    # Verify the child topic exists
                    child_fname = child_href.split("/")[-1]
                    if child_fname in ctx.topics:
                        collapsible.append(topichead)
        
        return collapsible
    
    # Find all collapsible sections
    collapsible_sections = _find_collapsible_sections(ctx.ditamap_root)
    
    for section_topichead in collapsible_sections:
        # Get the single content module child
        content_child = None
        for child in section_topichead:
            if child.tag == "topicref" and child.get("href"):
                content_child = child
                break
        
        if content_child is None:
            continue
            
        # Get the content module topic
        content_href = content_child.get("href")
        content_fname = content_href.split("/")[-1]
        content_topic = ctx.topics.get(content_fname)
        
        if content_topic is None:
            continue
        
        # Transfer section metadata to the content module
        section_navtitle = section_topichead.find("topicmeta/navtitle")
        if section_navtitle is not None and section_navtitle.text:
            # Update content topic title to match section
            content_title_el = content_topic.find("title")
            if content_title_el is not None:
                content_title_el.text = section_navtitle.text
        
        # Copy section attributes to content child
        for attr, value in section_topichead.attrib.items():
            content_child.set(attr, value)
        
        # Replace section with content module in the parent
        parent = section_topichead.getparent()
        if parent is not None:
            parent_index = list(parent).index(section_topichead)
            parent.remove(section_topichead)
            parent.insert(parent_index, content_child) 


def _optimize_remaining_sections(ctx: "DitaContext", depth_limit: int) -> None:
    """Optimize remaining sections by promoting solo children and creating content modules."""
    if ctx.ditamap_root is None:
        return
    
    max_iterations = 5
    for iteration in range(max_iterations):
        changes_made = False
        
        # Find all topichead sections that need optimization
        sections_to_optimize = []
        
        # Collect all sections in a single pass to avoid modification during iteration
        def _collect_sections(node):
            for child in list(node):  # Use list() to avoid modification issues
                if child.tag == "topichead":
                    topic_children = [c for c in child if c.tag == "topicref" and c.get("href")]
                    level = int(child.get("data-level", 1))
                    
                    if len(topic_children) == 1:
                        # Solo child - always optimize
                        sections_to_optimize.append(("solo", child, topic_children[0]))
                    elif len(topic_children) > 1 and level == depth_limit:
                        # Multi-child at target level - create content module
                        sections_to_optimize.append(("multi", child, topic_children))
                
                # Recurse into child sections
                _collect_sections(child)
        
        _collect_sections(ctx.ditamap_root)
        
        # Apply optimizations
        for opt_type, section, children in sections_to_optimize:
            if opt_type == "solo":
                _promote_solo_child_safe(ctx, section, children)
                changes_made = True
            elif opt_type == "multi":
                _create_content_module_safe(ctx, section, children)
                changes_made = True
        
        # If no changes were made, we're done
        if not changes_made:
            break


def _promote_solo_child_safe(ctx: "DitaContext", section: ET.Element, child: ET.Element) -> None:
    """Safely promote a solo child topic to replace its parent section."""
    try:
        # Update child's title to match section
        section_title_el = section.find("topicmeta/navtitle")
        if section_title_el is not None and section_title_el.text:
            # Update topic title
            child_href = child.get("href")
            if child_href:
                child_fname = child_href.split("/")[-1]
                topic_el = ctx.topics.get(child_fname)
                if topic_el is not None:
                    topic_title_el = topic_el.find("title")
                    if topic_title_el is not None:
                        topic_title_el.text = section_title_el.text
            
            # Update topicref navtitle
            child_navtitle = child.find("topicmeta/navtitle")
            if child_navtitle is not None:
                child_navtitle.text = section_title_el.text
        
        # Copy section attributes to child
        for attr, value in section.attrib.items():
            child.set(attr, value)
        
        # Replace section with child in parent
        parent = section.getparent()
        if parent is not None:
            section_index = list(parent).index(section)
            parent.remove(section)
            parent.insert(section_index, child)
    except Exception:
        # If promotion fails, skip silently
        pass


def _create_content_module_safe(ctx: "DitaContext", section: ET.Element, topic_children: list) -> None:
    """Safely create a content module for a section and merge children into it."""
    try:
        # Create content module
        content_module = _ensure_content_module(ctx, section)
        
        # Merge children into content module
        for child in topic_children[:]:  # Copy list to avoid modification issues
            child_href = child.get("href")
            if child_href:
                child_fname = child_href.split("/")[-1]
                topic_el = ctx.topics.get(child_fname)
                if topic_el is not None:
                    # Copy title as paragraph
                    title_el = topic_el.find("title")
                    if title_el is not None and title_el.text:
                        clean_title = " ".join(title_el.text.split())
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = clean_title
                        
                        content_body = content_module.find("conbody")
                        if content_body is None:
                            content_body = ET.SubElement(content_module, "conbody")
                        content_body.append(head_p)
                    
                    # Copy content
                    _copy_content(topic_el, content_module)
                    
                    # Remove child from section and clean up topic
                    if child in section:
                        section.remove(child)
                    ctx.topics.pop(child_fname, None)
    except Exception:
        # If merging fails, skip silently
        pass


def _final_cleanup_orphaned_topics(ctx: "DitaContext") -> None:
    """Remove any topics that are no longer referenced in the ditamap."""
    if ctx.ditamap_root is None:
        return
    
    # Collect all referenced topic files
    referenced_topics = set()
    for topicref in ctx.ditamap_root.findall('.//topicref[@href]'):
        href = topicref.get("href")
        if href:
            fname = href.split("/")[-1]
            referenced_topics.add(fname)
    
    # Remove unreferenced topics
    orphaned_topics = set(ctx.topics.keys()) - referenced_topics
    for fname in orphaned_topics:
        ctx.topics.pop(fname, None) 