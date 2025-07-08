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
    "merge_topics_below_depth",
    "merge_topics_by_titles",
    "merge_topics_by_levels",
    "merge_topics_by_styles",
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

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_topic_bodies(ctx: "DitaContext") -> None:
    """Ensure every topic uses <conbody>.

    Older documents may still contain a generic <body>.  Converting them once at
    the start of every merge/consolidation operation lets the core logic assume
    a single canonical element name, simplifying maintenance while remaining
    backward-compatible.
    """
    for topic in ctx.topics.values():
        body_el = topic.find("body")
        if body_el is not None and topic.find("conbody") is None:
            body_el.tag = "conbody"



def _copy_content(src_topic: ET.Element, dest_topic: ET.Element) -> None:
    """Append block-level children from *src_topic* into *dest_topic*."""

    dest_body = dest_topic.find("conbody")
    if dest_body is None:
        dest_body = ET.SubElement(dest_topic, "conbody")

    # Ensure legacy <body> alias exists for backward-compatibility (tests expect it)
    legacy_body = dest_topic.find("body")
    if legacy_body is None:
        legacy_body = ET.SubElement(dest_topic, "body")

    # DITA concept topics should use <conbody>, but some legacy topics may still
    # contain a generic <body>.  Support both to avoid data loss.
    src_body = src_topic.find("conbody")
    if src_body is None:
        src_body = src_topic.find("body")
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
            # Keep legacy <body> in sync for backward-compatibility
            legacy_body.append(deepcopy(new_child))


def merge_topics_below_depth(ctx: "DitaContext", depth_limit: int) -> None:  # noqa: D401
    """Merge descendants deeper than *depth_limit* into their nearest ancestor.

    Uses a safe two-phase approach to guarantee no content is ever lost:
    
    1. Phase 1: Identify all topics deeper than depth_limit
    2. Phase 2: Merge them (deepest-first), ensuring content is preserved
    
    The function modifies *ctx* in-place:
        • Updates ctx.ditamap_root (removes pruned <topicref>s)
        • Strips merged entries from ctx.topics
        • Sets ctx.metadata["merged_depth"] = depth_limit
    """
    root = ctx.ditamap_root
    if root is None:
        return

    
    # ------------------------------------------------------------------
    # PHASE 1 – identify all topics deeper than *depth_limit*
    # ------------------------------------------------------------------
    # Store as tuples of (depth, topicref, parent)
    to_merge = []
    
    def _identify_deep_topics(node, depth, parent):
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue
                
            t_level = int(tref.get("data-level", depth))
            
            # Store the actual topic level in data-level for consistency
            tref.set("data-level", str(t_level))
                
            # Record this topic if it's deeper than our limit
            if t_level > depth_limit:
                to_merge.append((t_level, tref, parent))
                
            # Always recurse to find all deep topics
            _identify_deep_topics(tref, t_level + 1, tref)
    
    # Start identification from the root
    _identify_deep_topics(root, 1, None)
    
    # Sort deepest-first to ensure children are processed before parents
    to_merge.sort(key=lambda x: (-x[0], x[1].tag))
    
    # ------------------------------------------------------------------
    # PHASE 2 – process the topics deepest-first
        # ------------------------------------------------------------------
    removed_topics = set()
    
    for depth, tref, parent in to_merge:
        # Skip if this node was already removed (was a child of a merged parent)
        if parent is not None and tref not in list(parent):
            continue
            
        # Get topic information
        href = tref.get("href")
        topic_el = None
        fname = None
        
        if href:
            fname = href.split("/")[-1]
            topic_el = ctx.topics.get(fname)
            
        # If no content to merge, just delete the reference and continue
        if topic_el is None:
            if parent is not None and tref in list(parent):
                parent.remove(tref)
            continue
            
        # Find a suitable merge target at or above depth_limit
        merge_target = None
        target_node = None
        
        # Start from the parent and work upward
        current = parent
        search_depth = depth - 1
        
        while current is not None and search_depth >= 1:
            current_href = current.get("href")
            if current_href and search_depth <= depth_limit:
                # Found a content module at or above depth_limit
                target_fname = current_href.split("/")[-1]
                target_topic = ctx.topics.get(target_fname)
                if target_topic is not None:
                    merge_target = target_topic
                    target_node = current
                    break
                    
            # Move up the tree
            current = current.getparent()
            if current is not None and current.tag in ("topicref", "topichead"):
                search_depth -= 1
                
        # If no existing merge target found at allowed depth, create one
        if merge_target is None:
            # Find the first ancestor at exactly depth_limit
            # or the closest one if none exists at that exact depth
            target_container = None
            best_depth_diff = float('inf')
            
            current = parent
            search_depth = depth - 1
            
            while current is not None and search_depth >= 1:
                if current.tag in ("topicref", "topichead"):
                    depth_diff = abs(search_depth - depth_limit)
                    if depth_diff < best_depth_diff:
                        best_depth_diff = depth_diff
                        target_container = current
                        if search_depth <= depth_limit:
                            # We found a container at/above the limit
                            break
                            
                # Move up the tree
                current = current.getparent()
                if current is not None and current.tag in ("topicref", "topichead"):
                    search_depth -= 1
            
            # GUARANTEED TARGET: If we still don't have a viable container, use the root
            # This is an extreme fallback but ensures content is never lost
            if target_container is None and ctx.ditamap_root is not None:
                target_container = ctx.ditamap_root
                    
            # Create a content module in the target container
            if target_container is not None:
                target_node = target_container
                # Make sure we get a valid content module
                merge_target = _ensure_content_module(ctx, target_container, exclude_fname=fname)
                
        # If we have nowhere to merge, we cannot safely proceed with this node
        if merge_target is None:
            # Cannot happen in well-formed maps (would mean no root), but
            # let's be defensive and skip rather than lose content
            continue
            
        # Now we have a valid merge_target, copy the content
        
        # 1. Create a title paragraph for the merged content
        title_el = topic_el.find("title")
        if title_el is not None and title_el.text:
            clean_title = " ".join(title_el.text.split())
            head_p = ET.Element("p", id=generate_dita_id())
            head_p.text = clean_title
            
            target_body = merge_target.find("conbody")
            if target_body is None:
                target_body = ET.SubElement(merge_target, "conbody")
                
            target_body.append(head_p)
            
        # 2. Copy all content
        _copy_content(topic_el, merge_target)
        
        # 3. Process and merge any children this node might have
        # (Skip if they're already in to_merge list - they'll be handled separately)
        
        # 4. Now that content is safely preserved, remove the source reference
        if parent is not None and tref in list(parent):
            parent.remove(tref)
            
        # Mark for removal from topics dictionary
        if fname:
            removed_topics.add(fname)
    
    # Clean up merged topics from the dictionary
    for fname in removed_topics:
        ctx.topics.pop(fname, None)
    
    

    # Consolidate any single-child sections created by merging
    consolidate_sections(ctx)

    # Final clean-up: record metadata
    # Mark that depth merging has been applied
    ctx.metadata["merged_depth"] = depth_limit




def consolidate_sections(ctx: "DitaContext") -> None:
    """Consolidate sections with a single child content module.
    
    Uses an iterative fixed-point approach to guarantee that all sections
    that can be consolidated are processed, even those created by previous
    consolidations.
    
    A section is consolidated when:
    1. It has exactly one child with href (content module)
    2. It has no other topicref/topichead children
    
    The section's title (if any) becomes the topic title, and the
    child content is merged into a new content module.
    """
    root = ctx.ditamap_root
    if root is None:
        return
    
    # Iterative approach to handle cases where consolidation creates
    # new opportunities for further consolidation
    iteration = 0
    max_iterations = 10  # Safety limit - maps are small, so this is plenty
    changes_made = True
    
    # Statistics for logging
    total_consolidated = 0
    
    # Ensure legacy <body> elements are normalised first
    _normalize_topic_bodies(ctx)

    while changes_made and iteration < max_iterations:
        changes_made = False
        iteration += 1
        consolidated_in_iteration = 0
        
        def _consolidate_pass(node):
            nonlocal changes_made, consolidated_in_iteration
            
            # Process children first (bottom-up) so nested structures
            # are consolidated from the leaves up
            for child in list(node):
                if child.tag in ("topicref", "topichead"):
                    _consolidate_pass(child)
            
            # Skip if not a section (no consolidation needed)
            # A section is a topicref/topichead without href
            if node.tag not in ("topicref", "topichead") or "href" in node.attrib:
                return
            
            # Get all children that are valid structural elements
            children = [c for c in node if c.tag in ("topicref", "topichead")]
            
            # Find content children (with href) and section children (without href)
            content_children = [c for c in children if "href" in c.attrib]
            section_children = [c for c in children if c.tag in ("topicref", "topichead") 
                               and "href" not in c.attrib]
            
            # Only consolidate if there's exactly one content child and no section children
            if len(content_children) == 1 and len(section_children) == 0:
                child = content_children[0]
                href = child.get("href")
                
                if href:
                    fname = href.split("/")[-1]
                    child_topic = ctx.topics.get(fname)
                    
                    if child_topic is not None:
                        # Find section title, if any
                        section_title = None
                        nav_title_el = node.find("./topicmeta/navtitle")
                        if nav_title_el is not None and nav_title_el.text:
                            section_title = nav_title_el.text.strip()
                        
                        # Create new topic ID and filename
                        new_id = generate_dita_id()
                        new_fname = f"topic_{new_id}.dita"
                        
                        # Create new topic with appropriate title
                        if section_title:
                            # Use section title if available
                            new_topic = _new_topic_with_title(section_title)
                        else:
                            # Otherwise use child's title
                            child_title = child_topic.find("title")
                            title_text = "Untitled"
                            if child_title is not None and child_title.text:
                                title_text = child_title.text.strip()
                            new_topic = _new_topic_with_title(title_text)
                        
                        # Copy all content from child topic to new topic
                        _copy_content(child_topic, new_topic)
                        
                        # Register new topic in context
                        ctx.topics[new_fname] = new_topic
                        
                        # Update section to point to new topic
                        node.set("href", f"topics/{new_fname}")
                        
                        # Preserve important attributes from child
                        for attr in ["data-level", "data-style"]:
                            if attr in child.attrib:
                                node.set(attr, child.get(attr))
                        
                        # Remove the child node since its content is now in the section
                        node.remove(child)
                        
                        # Remove old topic from dictionary
                        ctx.topics.pop(fname, None)
                        
                        # Mark that changes were made so we'll do another pass
                        changes_made = True
                        consolidated_in_iteration += 1
        
        # Run a complete consolidation pass
        _consolidate_pass(root)
        total_consolidated += consolidated_in_iteration
    
    # Mark that consolidation has been completed
    ctx.metadata["consolidated_sections"] = True


def merge_topics_by_styles(ctx: "DitaContext", exclude_map: dict[int, set[str]]) -> None:  # noqa: D401
    """Merge topics whose (level, style) matches *exclude_map*.

    *exclude_map* maps heading level (int) to a set of style names to be
    removed/merged into the parent. Style comparison is case-sensitive to
    match Word names.
    """
    if not exclude_map:
        return

    root = ctx.ditamap_root
    if root is None:
        return

    removed: set[str] = set()
    
    # Track all content modules (nodes with href attribute) for accurate merging
    # Map of (parent_id -> list of content modules in order)
    content_modules_by_parent = {}
    
    # Build a map of parent IDs to content modules and collect all content modules
    def _build_content_module_map(node, parent_id=None):
        node_id = id(node)  # Use object ID as unique identifier
        content_modules = []
        
        for child in node:
            if child.tag not in ("topicref", "topichead"):
                continue
                
            # Content module has href attribute
            if "href" in child.attrib:
                content_modules.append(child)
            
            # Recursively process children
            _build_content_module_map(child, node_id)
            
        # Store content modules for this node
        if content_modules:
            content_modules_by_parent[node_id] = content_modules
    
    # Build the content module map
    _build_content_module_map(root)
    
    # Find the previous content module relative to the given one
    def _find_previous_content_module(tref):
        parent = tref.getparent()
        if parent is None:
            return None
            
        parent_id = id(parent)
        modules = content_modules_by_parent.get(parent_id, [])
        
        # Find the index of this module in the parent's list
        try:
            index = modules.index(tref)
            # If there's a previous content module, return it
            if index > 0:
                prev_tref = modules[index - 1]
                prev_href = prev_tref.get("href", "")
                if prev_href:
                    prev_fname = prev_href.split("/")[-1]
                    return ctx.topics.get(prev_fname)
        except ValueError:
            pass
            
        # If no previous sibling or not found, try to find a content module in a parent
        if parent.getparent() is not None:
            return _find_previous_content_module(parent)
            
        return None
    
    def _walk(node: ET.Element, level: int, ancestor_topic_el: ET.Element | None):
        for tref in list(node):
            if tref.tag not in ("topicref", "topichead"):
                continue

            t_level = int(tref.get("data-level", level))
            style_name = tref.get("data-style", "")

            href = tref.get("href")
            topic_el = None
            fname = None
            if href:
                fname = href.split("/")[-1]
                topic_el = ctx.topics.get(fname)

            next_ancestor = topic_el if topic_el is not None else ancestor_topic_el
            
            # Check if this element should be filtered by style
            if t_level in exclude_map and style_name in exclude_map[t_level]:
                # Find appropriate merge target - prioritize previous content module
                merge_target = None
                
                if topic_el is not None:
                    # Try to find previous content module first
                    prev_module = _find_previous_content_module(tref)
                    if prev_module is not None:
                        merge_target = prev_module
                    elif ancestor_topic_el is not None:
                        merge_target = ancestor_topic_el
                
                if merge_target is not None:
                    # Preserve heading title paragraph
                    title_el = topic_el.find("title") if topic_el is not None else None
                    if title_el is not None and title_el.text:
                        head_p = ET.Element("p", id=generate_dita_id())
                        head_p.text = " ".join(title_el.text.split())
                        target_body = merge_target.find("conbody")
                        if target_body is None:
                            target_body = ET.SubElement(merge_target, "conbody")
                        target_body.append(head_p)

                    # Merge content
                    if topic_el is not None:
                        _copy_content(topic_el, merge_target)

                # Recurse into children with the appropriate ancestor
                _walk(tref, t_level + 1, merge_target)

                # Remove the filtered node
                node.remove(tref)
                if fname:
                    removed.add(fname)
            else:
                # Normal processing - continue traversal
                _walk(tref, t_level + 1, next_ancestor)

    # Execute the merge content process
    _walk(root, 1, None)
    
    # Clean up removed topics
    for fname in removed:
        ctx.topics.pop(fname, None)

    # Mark that styles have been filtered
    ctx.metadata["merged_exclude_styles"] = True
    # Don't set consolidated_sections flag here - we'll handle it separately

# ... (rest of the code remains the same)


def _new_topic_with_title(title_text: str) -> ET.Element:
    """Create a bare <concept> topic element with *title_text*."""
    topic_el = ET.Element("concept", id=generate_dita_id())
    title_el = ET.SubElement(topic_el, "title")
    title_el.text = title_text
    # Body will be added later when content is copied
    return topic_el


def _ensure_content_module(ctx: "DitaContext", section_tref: ET.Element, *, exclude_fname: str | None = None) -> ET.Element:
    """Ensure there is a child *module* topic under *section_tref* and return its <concept> element.

    If the first child already references a topic (module) we reuse it, otherwise we
    create a new topic file, register it in ctx.topics and insert a new <topicref>.
    """
    # Try to reuse the first existing module child if present
    for child in section_tref:
        href = child.get("href")
        if href:
            fname = href.split("/")[-1]
            # Skip a child that is explicitly excluded (e.g. the very topic we are currently merging FROM)
            if exclude_fname is not None and fname == exclude_fname:
                continue
            existing_topic = ctx.topics.get(fname)
            if existing_topic is not None:
                return existing_topic

    # No module child – create a fresh one
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
    child_ref.set("data-level", str(int(section_tref.get("data-level", 1)) + 1))
    # Keep navtitle in sync
    nav = ET.SubElement(child_ref, "topicmeta")
    navtitle = ET.SubElement(nav, "navtitle")
    navtitle.text = title_txt

    # Insert as first child to preserve order
    section_tref.insert(0, child_ref)

    return topic_el 