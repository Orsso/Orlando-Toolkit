# -*- coding: utf-8 -*-
"""Service for consolidating DITA structures.

This module provides a service for consolidating DITA structures according to
Orlando DITA rules. It implements the consolidation rule (FR6.4) which states
that if a topic is the sole child of a container, it must be promoted and
the container removed.
"""

from __future__ import annotations
from copy import deepcopy
from typing import Dict, List, Optional, Set, TYPE_CHECKING
from lxml import etree as ET  # type: ignore

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


class ConsolidationService:
    """Service for consolidating DITA structures according to Orlando rules.
    
    This service is responsible for implementing the consolidation rule (FR6.4)
    which states that if a topic is the sole child of a container, it must be
    promoted and the container removed.
    """
    
    def consolidate_sections(self, context: DitaContext) -> DitaContext:
        """FR6.4: Consolidate sections with a single content child.
        
        This implements Functional Requirement 6.4: Consolidation.
        If a section (topichead) has exactly one topicref child, the
        child is promoted and the section is removed, unless the section
        has had content merged into it.
        
        Args:
            context: The DitaContext to process
            
        Returns:
            A new DitaContext with consolidated structure
        """
        # Create a new context to avoid modifying the input
        result = deepcopy(context)
        
        # Track sections that have had content merged into them
        sections_with_merged_content = set()
        if "sections_with_merged_content" in result.metadata:
            sections_with_merged_content = set(result.metadata["sections_with_merged_content"])
        
        # Find all candidate sections for consolidation
        consolidation_candidates = []
        
        def find_candidates(node, parent=None):
            # Check if this is a section (topichead)
            if node.tag == "topichead":
                # Check if this section has exactly one child that is a topicref with href
                content_children = [child for child in node if child.tag == "topicref" and child.get("href")]
                
                if len(content_children) == 1 and parent is not None:
                    # Don't consolidate sections that have had content merged into them
                    node_id = node.get("id")
                    if node_id not in sections_with_merged_content:
                        consolidation_candidates.append((node, parent, content_children[0]))
            
            # Recurse to children (even if this node is a candidate)
            for child in node:
                if child.tag in ("topichead", "topicref"):
                    find_candidates(child, node)
        
        # Start the search from the root
        find_candidates(result.ditamap_root)
        
        # Process each candidate in reverse order (bottom-up)
        # This ensures that nested candidates are processed correctly
        for section, parent, content in reversed(consolidation_candidates):
            # Copy attributes from section to content where they don't already exist
            # This preserves metadata like data-level
            for attr, value in section.attrib.items():
                if attr not in content.attrib and attr != "id":
                    content.set(attr, value)
            
            # Preserve section title in promoted content
            section_navtitle_el = section.find("topicmeta/navtitle")
            if section_navtitle_el is not None and section_navtitle_el.text:
                # Ensure content has topicmeta/navtitle
                content_topicmeta = content.find("topicmeta")
                if content_topicmeta is None:
                    content_topicmeta = ET.SubElement(content, "topicmeta")
                content_navtitle = content_topicmeta.find("navtitle")
                if content_navtitle is None:
                    content_navtitle = ET.SubElement(content_topicmeta, "navtitle")
                content_navtitle.text = section_navtitle_el.text

            # Replace the section with its content in the parent
            section_idx = list(parent).index(section)
            parent.remove(section)
            parent.insert(section_idx, content)
        
        # Mark that we've processed this rule
        result.metadata["consolidated"] = True
        return result
