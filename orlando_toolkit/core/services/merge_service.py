# -*- coding: utf-8 -*-
"""Service for merging DITA topics.

This module provides a service for merging DITA topics according to
the Orlando DITA compliance rules. It handles merging by level,
merging by style, and executing individual merge operations.
"""

from __future__ import annotations
from copy import deepcopy
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING
from lxml import etree as ET  # type: ignore
from uuid import uuid4

from orlando_toolkit.core.utils import generate_dita_id
from orlando_toolkit.core.services.structure_models import MergeOperation, TopicIdentifier

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


class MergeService:
    """Service for merging DITA topics according to Orlando rules.
    
    This service is responsible for all merge operations on DITA topics,
    including merging by level (FR6.1), merging by style (FR6.2), and
    executing individual merge operations (FR6.3).
    """
    
    def merge_topics_by_level(self, context: DitaContext, max_depth: int) -> DitaContext:
        """FR6.1: Merge topics deeper than the specified level.
        
        This implements Functional Requirement 6.1: Merge by heading level.
        Any topic deeper than max_depth will be merged with its parent.
        
        Args:
            context: The DitaContext containing the topics
            max_depth: Maximum depth for topics to remain separate
            
        Returns:
            A new DitaContext with the merged structure
        """
        # Create a new context to avoid modifying the input
        result = deepcopy(context)
        
        # Store topic IDs that need to be completely removed after merging
        topics_to_remove_by_id = set()
        
        # Track sections that have had topics merged into them to prevent consolidation
        sections_with_merged_content = set()
        
        # First pass: Identify topics to merge and their targets
        merge_operations = []
        
        def identify_topics_to_merge(node, level=1, parent=None):
            # Process all children first (depth-first)
            children_to_process = list(node)  # Create a copy to avoid modification issues
            
            for child in children_to_process:
                if child.tag in ("topicref", "topichead"):
                    identify_topics_to_merge(child, level + 1, node)
            
            # Now check if this node should be merged
            if node.tag in ("topicref", "topichead"):
                # Use data-level if available, otherwise use traversal level
                node_level = int(node.get("data-level", level))
                
                if node_level > max_depth and parent is not None and node.tag == "topicref" and node.get("href"):
                    # Find the target for this node
                    target_href = parent.get("href")
                    
                    if not target_href and parent.tag == "topichead":
                        # Parent is a container, we'll need to find or create a content module
                        # Just store the parent for now, we'll resolve targets in the next phase
                        merge_operations.append((node, parent))
                        # Store ID for complete removal
                        if node.get("id"):
                            topics_to_remove_by_id.add(node.get("id"))
                    elif target_href:
                        # Parent has content, merge directly
                        merge_operations.append((node, parent))
                        # Store ID for complete removal
                        if node.get("id"):
                            topics_to_remove_by_id.add(node.get("id"))
        
        # Start the identification process
        identify_topics_to_merge(result.ditamap_root)
        
        # Second pass: Execute merge operations
        for tref, parent_tref in merge_operations:
            # Skip if the tref was removed in a previous operation
            if tref.get("id") and tref.get("id") not in topics_to_remove_by_id:
                continue
                
            # Find target href
            target_href = parent_tref.get("href")
            
            if not target_href and parent_tref.tag == "topichead":
                # Parent is a container, find or create a content module
                target_topic = self._ensure_content_module(result, parent_tref)
                if target_topic is None:
                    continue  # Couldn't create a target
                    
                # Get the href of the newly created/found topic
                for child in parent_tref:
                    if child.tag == "topicref" and child.get("href"):
                        target_href = child.get("href")
                        break
                
                # Mark this parent as having had content merged into it
                if parent_tref.get("id"):
                    sections_with_merged_content.add(parent_tref.get("id"))
            
            if not target_href:
                continue  # No valid target
                
            # Create merge operation
            operation = MergeOperation(
                source_id=TopicIdentifier.from_element(tref),
                target_id=TopicIdentifier(element_id="", href=target_href),
                reason="depth_rule",
                preserve_title=True
            )
            
            # Execute the merge operation
            self._execute_merge_operation(result, operation)
        
        # Third pass: Remove all merged topics from the structure
        def remove_topics_by_id(node):
            # Create a list of children to potentially remove
            children_to_remove = []
            
            # First, check each child
            for child in node:
                if child.tag in ("topicref", "topichead") and child.get("id") and child.get("id") in topics_to_remove_by_id:
                    # This child should be removed
                    children_to_remove.append(child)
                else:
                    # Process this child's children recursively
                    remove_topics_by_id(child)
            
            # Now remove the children we identified
            for child in children_to_remove:
                node.remove(child)
        
        # Start the removal process from the root
        remove_topics_by_id(result.ditamap_root)
        
        # Mark that we've processed this rule
        result.metadata["merged_depth"] = max_depth
        # Store the IDs of sections that have had content merged into them
        result.metadata["sections_with_merged_content"] = list(sections_with_merged_content)
        return result
    
    def merge_topics_by_styles(self, context: DitaContext, excluded_styles: Dict[int, Set[str]]) -> DitaContext:
        """FR6.2: Merge topics with specified styles.
        
        This implements Functional Requirement 6.2: Merge by style.
        Any topic with a style in the excluded_styles set for its level
        will be merged with its parent.
        
        Args:
            context: The DitaContext to process
            excluded_styles: Dict mapping heading levels to sets of excluded style names
            
        Returns:
            A new DitaContext with style-based merging applied
        """
        # Create a new context to avoid modifying the input
        result = deepcopy(context)
        
        # If no excluded styles, return unchanged
        if not excluded_styles:
            return result
            
        # Find all topics with excluded styles
        topics_to_merge = []
        
        def traverse(node, level=1, parent=None):
            # Check if this is a topic reference
            if node.tag == "topicref" and parent is not None:
                # Check if it has a style that should be excluded
                node_level = int(node.get("data-level", level))
                style = node.get("style", "")
                
                if node_level in excluded_styles and style in excluded_styles[node_level]:
                    topics_to_merge.append((node, parent))
                    
            # Recurse to children
            for child in node:
                traverse(child, level + 1, node)
                
        # Start from the root
        traverse(result.ditamap_root)
        
        # Track sections that have had content merged into them
        sections_with_merged_content = set()
        if "sections_with_merged_content" in result.metadata:
            sections_with_merged_content = set(result.metadata["sections_with_merged_content"])
        
        # Process each topic to merge
        for tref, parent_tref in topics_to_merge:
            # Identify the target for merging
            target_href = parent_tref.get("href")
            
            if not target_href and parent_tref.tag == "topichead":
                # Parent is a container, find or create a content module
                target_topic = self._ensure_content_module(result, parent_tref)
                if target_topic is None:
                    continue  # Couldn't create a target
                    
                # Get the href of the newly created/found topic
                for child in parent_tref:
                    if child.tag == "topicref" and child.get("href"):
                        target_href = child.get("href")
                        break
                        
                # Mark this section as having merged content
                if parent_tref.get("id"):
                    sections_with_merged_content.add(parent_tref.get("id"))
            
            if not target_href:
                continue  # No valid target
                
            # Create merge operation
            operation = MergeOperation(
                source_id=TopicIdentifier.from_element(tref),
                target_id=TopicIdentifier(element_id="", href=target_href),
                reason="style_rule",
                preserve_title=True
            )
            
            self._execute_merge_operation(result, operation)
            
            # Remove the merged topic reference
            parent_tref.remove(tref)
            
            # Keep merged topics in the dictionary to maintain references
        
        # Update the metadata
        result.metadata["sections_with_merged_content"] = list(sections_with_merged_content)
        return result
        
    def _execute_merge_operation(self, context: DitaContext, operation: MergeOperation) -> bool:
        """FR6.3: Execute a merge operation with ID uniqueness enforcement.
        
        This implements Functional Requirement 6.3: ID uniqueness and reference update.
        Merges content from the source topic into the target topic, preserving all content,
        regenerating IDs to ensure uniqueness, and updating all internal references.
        
        Args:
            context: The DitaContext to modify
            operation: The merge operation to execute
            
        Returns:
            True if the merge was successful, False otherwise
        """
        # Find the source and target topics
        source_topic = self._find_topic_by_identifier(context, operation.source_id)
        target_topic = self._find_topic_by_identifier(context, operation.target_id)
        
        if source_topic is None or target_topic is None:
            return False  # Can't merge if either topic is missing
            
        # Generate new IDs for all elements in the source topic to ensure uniqueness
        id_mapping = self._generate_new_ids(source_topic)
        
        # Copy all content from source to target
        self._copy_content(source_topic, target_topic, id_mapping)
        
        # Update all references in the context to the new IDs
        self._update_all_references(context, id_mapping)
        
        # Return success
        return True
        
    def _find_topic_by_identifier(self, context: DitaContext, identifier: TopicIdentifier) -> Optional[ET.Element]:
        """Find a topic element by its identifier.
        
        Args:
            context: The DitaContext to search
            identifier: The identifier to look for
            
        Returns:
            The topic element if found, None otherwise
        """
        # If we have an href, look up the topic directly
        if identifier.href:
            # Try by full path first
            filename = identifier.href.split("/")[-1]
            
            if filename in context.topics:
                return context.topics[filename]
                
        # If we have an element ID, search for it
        if identifier.element_id:
            # First check the ditamap
            for node in context.ditamap_root.xpath(".//*[@id='" + identifier.element_id + "']"):
                # If it's a topicref with href, get the referenced topic
                if node.tag == "topicref" and node.get("href"):
                    filename = node.get("href").split("/")[-1]
                    if filename in context.topics:
                        return context.topics[filename]
                        
            # Then check all topics
            for topic in context.topics.values():
                if topic.get("id") == identifier.element_id:
                    return topic
                    
        return None
        
    def _ensure_content_module(self, context: DitaContext, section_tref: ET.Element) -> Optional[ET.Element]:
        """Ensure a section has a content module.
        
        If the section already has a content module, returns it.
        Otherwise, creates a new content module and adds a reference to it.
        
        Args:
            context: The DitaContext to modify
            section_tref: The topichead element to ensure has content
            
        Returns:
            The concept element for the content module, or None if error
        """
        # Check if the section already has a content module
        for child in section_tref:
            if child.tag == "topicref" and child.get("href"):
                # Found an existing content module, look up the topic
                filename = child.get("href").split("/")[-1]
                if filename in context.topics:
                    return context.topics[filename]
                    
        # No content module found, create one
        section_id = section_tref.get("id", generate_dita_id())
        navtitle = section_tref.find("topicmeta/navtitle")
        title_text = navtitle.text if navtitle is not None and navtitle.text else "Content Module"
        
        # Create a new topic file
        topic = ET.Element("concept", id=section_id + "_content")
        
        # Add required elements (title, prolog, conbody)
        title = ET.SubElement(topic, "title", id=generate_dita_id())
        title.text = title_text
        
        prolog = ET.SubElement(topic, "prolog", id=generate_dita_id())
        critdates = ET.SubElement(prolog, "critdates", id=generate_dita_id())
        metadata = ET.SubElement(prolog, "metadata", id=generate_dita_id())
        
        conbody = ET.SubElement(topic, "conbody", id=generate_dita_id())
        
        # Generate a filename and add to context
        filename = f"section_{section_id}_content.dita"
        path = f"topics/{filename}"
        context.topics[filename] = topic
        
        # Add the path to metadata if needed
        if "topic_paths" not in context.metadata:
            context.metadata["topic_paths"] = {}
        context.metadata["topic_paths"][filename] = path
        
        # Add a topicref to the section
        topicref = ET.SubElement(section_tref, "topicref", 
                                id=generate_dita_id(),
                                href=path,
                                locktitle="yes")
                                
        # Add required metadata to the topicref
        topicmeta = ET.SubElement(topicref, "topicmeta")
        navtitle = ET.SubElement(topicmeta, "navtitle")
        navtitle.text = title_text
        critdates = ET.SubElement(topicmeta, "critdates")
        othermeta = ET.SubElement(topicmeta, "othermeta",
                                 name="tocIndex",
                                 content="1")
                                 
        return topic
        
    def _generate_new_ids(self, source_topic: ET.Element) -> Dict[str, str]:
        """Generate new IDs for all elements in the source topic.
        
        Creates a mapping from old IDs to new IDs for all elements in the source
        that will be copied to the target.
        
        Args:
            source_topic: The source topic element
            
        Returns:
            Dictionary mapping old IDs to new IDs
        """
        id_mapping = {}
        
        # Process the topic element and all its descendants
        for element in source_topic.xpath(".//*[@id]"):
            old_id = element.get("id")
            if old_id:
                new_id = generate_dita_id()
                id_mapping[old_id] = new_id
                
        return id_mapping
    
    def _copy_content(self, source_topic: ET.Element, target_topic: ET.Element, id_mapping: Dict[str, str]) -> None:
        """Copy all content from source_topic to target_topic.
        
        This method copies all block-level content from source to target,
        excluding the title and prolog sections which are not merged.
        
        Args:
            source_topic: Source topic element
            target_topic: Target topic element
            id_mapping: Mapping of old IDs to new IDs
        """
        # Find source conbody
        source_conbody = source_topic.find("conbody")
        if source_conbody is None:
            return  # Nothing to copy
            
        # Find or create target conbody
        target_conbody = target_topic.find("conbody")
        if target_conbody is None:
            target_conbody = ET.SubElement(target_topic, "conbody", id=generate_dita_id())
            
        # Copy all children from source conbody to target conbody
        for child in list(source_conbody):
            # Create a deep copy of the element
            child_copy = deepcopy(child)

            # Update ID on the root of the copied element, if present
            root_old_id = child_copy.get("id")
            if root_old_id and root_old_id in id_mapping:
                child_copy.set("id", id_mapping[root_old_id])

            # Update IDs in all descendants of the copy
            for element in child_copy.xpath(".//*[@id]"):
                old_id = element.get("id")
                if old_id in id_mapping:
                    element.set("id", id_mapping[old_id])

            # Add the modified copy to the target
            target_conbody.append(child_copy)
    
    def _update_references(self, element: ET.Element, id_mapping: Dict[str, str]) -> None:
        """Update all references in an element according to the ID mapping.
        
        This method updates all href and conref attributes in the element
        and its descendants to point to the new IDs.
        
        Args:
            element: The element to update references in
            id_mapping: Mapping of old IDs to new IDs
        """
        # Update href attributes that reference local IDs
        for ref in element.xpath(".//*[@href]"):
            href = ref.get("href")
            if href and href.startswith("#"):
                # Local reference
                id_ref = href[1:]  # Remove the '#'
                if id_ref in id_mapping:
                    ref.set("href", f"#{id_mapping[id_ref]}")
        
        # Update conref attributes
        for ref in element.xpath(".//*[@conref]"):
            conref = ref.get("conref")
            if conref and "#" in conref:
                # Split into filename and ID parts
                parts = conref.split("#")
                if len(parts) == 2 and parts[1] in id_mapping:
                    ref.set("conref", f"{parts[0]}#{id_mapping[parts[1]]}")
    
    def _update_all_references(self, context: DitaContext, id_mapping: Dict[str, str]) -> None:
        """Update all references in the entire context.
        
        This method updates all references in all topics in the context
        to point to the new IDs.
        
        Args:
            context: The DitaContext to update
            id_mapping: Mapping of old IDs to new IDs
        """
        # Update all topics
        for topic in context.topics.values():
            self._update_references(topic, id_mapping)
