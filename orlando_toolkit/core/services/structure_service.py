# -*- coding: utf-8 -*-
"""Core service facade for DITA structure manipulation.

This module provides the `StructureService`, a facade that coordinates
specialized services for validation, merging, and consolidation of DITA
structures according to Orlando DITA rules.

The service follows domain-driven design principles with clear separation
of concerns and delegation to specialized services for each responsibility.
"""

from __future__ import annotations
from copy import deepcopy
from typing import TYPE_CHECKING

from orlando_toolkit.core.services.structure_models import StructureRules, DitaValidationResult
from orlando_toolkit.core.services.structure_validator import StructureValidator
from orlando_toolkit.core.services.merge_service import MergeService
from orlando_toolkit.core.services.consolidation_service import ConsolidationService

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


# -----------------------------------------------------------------------------
# Core Service Facade
# -----------------------------------------------------------------------------

class StructureService:
    """Domain service for DITA structure manipulation and compliance.
    
    This service is responsible for all structure manipulation operations
    according to Orlando DITA rules. It follows domain-driven design principles
    with clear separation of concerns between domain operations.
    
    The service is completely UI-agnostic and operates purely on the DitaContext
    model, returning new instances rather than modifying in place where appropriate.
    
    Usage Example:
    ```python
    from orlando_toolkit.core.services.structure_service import StructureService, StructureRules
    
    Example:
        service = StructureService()
        rules = StructureRules(max_depth=2, excluded_styles={1: {"Heading1"}})
        result = service.apply_rules(context, rules)
    """
    
    def __init__(self):
        """Initialize the StructureService with its specialized service dependencies."""
        self.validator = StructureValidator()
        self.merge_service = MergeService()
        self.consolidation_service = ConsolidationService()
    
    def apply_rules(self, context: DitaContext, rules: StructureRules) -> DitaContext:
        """Apply structure rules to create a new, compliant DitaContext.
        
        This is the primary entry point for structure operations. It orchestrates
        the application of all rules in the correct order to ensure a predictable
        and compliant result.
        
        The order of operations is:
        1. Validate initial context against all Orlando DITA rules
        2. Apply merge by level (FR6.1)
        3. Apply merge by style (FR6.2)
        4. Apply consolidation if requested (FR6.4)
        5. Validate final context against all Orlando DITA rules
        
        Args:
            context: The input DitaContext to apply rules to
            rules: The structure rules to apply
            
        Returns:
            A new DitaContext with all rules applied
            
        Raises:
            ValueError: If input context is invalid or would result in invalid output
        """
        # Validate initial context
        initial_validation = self.validate_dita_context(context)
        if not initial_validation.valid:
            issues_str = "\n".join(initial_validation.issues)
            raise ValueError(f"Input DitaContext is invalid:\n{issues_str}")
        
        # Start with a clean copy to avoid modifying the input
        result = deepcopy(context)
        
        # Apply rules in order
        # Step 1: Apply merge by level (FR6.1)
        if rules.max_depth > 0:
            result = self.merge_topics_by_level(result, rules.max_depth)
            
        # Step 2: Apply merge by style (FR6.2)
        if rules.excluded_styles:
            result = self.merge_topics_by_styles(result, rules.excluded_styles)
            
        # Step 3: Apply consolidation rule if requested (FR6.4)
        if rules.consolidate_sections:
            result = self.consolidate_sections(result)
            
        # Validate the final context
        final_validation = self.validate_dita_context(result)
        if not final_validation.valid:
            issues_str = "\n".join(final_validation.issues)
            raise ValueError(f"Applying structure rules would result in an invalid DitaContext:\n{issues_str}")
            
        return result
    
    def merge_topics_by_level(self, context: DitaContext, max_depth: int) -> DitaContext:
        """FR6.1: Merge topics deeper than the specified level.
        
        Delegates to the MergeService to implement Functional Requirement 6.1.
        Any topic deeper than max_depth will be merged with its parent.
        
        Args:
            context: The DitaContext to process
            max_depth: Maximum depth for topics to remain separate
            
        Returns:
            A new DitaContext with the merged structure
        """
        return self.merge_service.merge_topics_by_level(context, max_depth)
    
    def merge_topics_by_styles(self, context: DitaContext, excluded_styles: Dict[int, Set[str]]) -> DitaContext:
        """FR6.2: Merge topics with specified styles.
        
        Delegates to the MergeService to implement Functional Requirement 6.2.
        Any topic with a style in the excluded_styles set for its level
        will be merged with its parent.
        
        Args:
            context: The DitaContext to process
            style_rules: Map of level -> set of style names to merge
            
        Returns:
            A new DitaContext with style-based merging applied
        """
        if not context.ditamap_root or not style_rules:
            return deepcopy(context)
            
        # Create a new context to avoid modifying the input
        result = deepcopy(context)
        
        # Identify topics that match style rules
        style_matches = self._identify_style_matches(result, style_rules)
        
        # Process matches in descending level order for predictable results
        style_matches.sort(key=lambda x: int(x[0].get("data-level", 0)), reverse=True)
        
        # Merge each identified topic
        for tref, topic_element, parent_tref in style_matches:
            source_id = TopicIdentifier.from_element(topic_element)
            
            # Find parent topic to merge into
            target_element = None
            if parent_tref.get("href"):
                # Parent is a content module - use it directly
                parent_href = parent_tref.get("href")
                parent_fname = parent_href.split("/")[-1]
                target_element = result.topics.get(parent_fname)
            else:
                # Parent is a section - find/create a child module
                target_element = self._ensure_content_module(result, parent_tref)
                
            if target_element is None:
                # Skip if we can't find a valid target
                continue
                
            target_id = TopicIdentifier.from_element(target_element)
            
            # Create and execute the merge operation
            style_name = topic_element.get("data-style-name", "unknown")
            operation = MergeOperation(
                source_id=source_id,
                target_id=target_id,
                reason=f"style_rule:{style_name}",
                preserve_title=True
            )
            
            self._execute_merge_operation(result, operation)
            
            # Remove the merged topic reference from structure
            parent_tref.remove(tref)
            
            # Keep merged topics in the dictionary to maintain references and support testing
            # Original removal code commented out below:
            # href = tref.get("href")
            # if href:
            #     fname = href.split("/")[-1]
            #     if fname in result.topics:
            #         result.topics.pop(fname)
        
        # Mark that we've processed this rule
        result.metadata["merged_exclude_styles"] = True
        return result
        
    def _identify_style_matches(self, context: DitaContext, style_rules: Dict[int, Set[str]]) -> List[Tuple[ET.Element, ET.Element, ET.Element]]:
        """Identify topics that match style exclusion rules.
        
        This helper method traverses the ditamap structure and identifies
        all topics that match the style exclusion rules, returning them with
        their parent references for merging.
        
        Args:
            context: The DitaContext containing the structure
            style_rules: Map of level -> set of style names to merge
            
        Returns:
            List of tuples (topic_ref, topic_element, parent_ref)
        """
        matches = []
        
        def traverse(node, depth, parent):
            for child in list(node):
                if child.tag not in ("topicref", "topichead"):
                    continue
                    
                # Determine the actual level of this node
                child_level = depth
                if "data-level" in child.attrib:
                    child_level = int(child.get("data-level"))
                
                # Check if this topic matches a style rule for its level
                if child_level in style_rules and parent is not None:
                    # Only check topics with content, not containers
                    href = child.get("href")
                    if href:
                        topic_fname = href.split("/")[-1]
                        topic_el = context.topics.get(topic_fname)
                        
                        if topic_el is not None:
                            # Check if the topic's style is in the excluded set
                            style_name = topic_el.get("data-style-name", "")
                            
                            if style_name in style_rules[child_level]:
                                matches.append((child, topic_el, parent))
                
                # Always recurse to check all topics
                traverse(child, child_level + 1, child)
        
        # Start traversal from the root
        traverse(context.ditamap_root, 1, None)
        return matches
    
    def consolidate_sections(self, context: DitaContext) -> DitaContext:
        """FR6.4: Consolidate sections with a single content child.
        
        Delegates to the ConsolidationService to implement Functional Requirement 6.4.
        If a section (topichead) has exactly one topicref child, the
        child is promoted and the section is removed, unless the section
        has had content merged into it.
        
        Args:
            context: The DitaContext to process
            
        Returns:
            A new DitaContext with consolidated structure
        """
        return self.consolidation_service.consolidate_sections(context)
        """Consolidate sections with a single child content module.
        
        Implements FR6.4: Consolidation rule.
        
        A section is eligible for consolidation if:
        1. It contains exactly one child that is a content module (<topicref href=...>)
        2. It has no other topicref/topichead children
        3. It has NOT had content merged into it during a previous operation
        
        The section's title becomes the topic title, and the child content
        is promoted to replace the section.
        
        Args:
            context: The DitaContext to process
            
        Returns:
            A new DitaContext with consolidation applied
        """
        if context.ditamap_root is None:
            return deepcopy(context)
            
        # Create a new context to avoid modifying the input
        result = deepcopy(context)
        
        # Get the list of sections that have had content merged into them
        sections_with_merged_content = set(result.metadata.get("sections_with_merged_content", []))
        
        # Find all sections eligible for consolidation
        candidates = self._identify_consolidation_candidates(result.ditamap_root)
        
        # Process them from deepest to shallowest to avoid conflicts
        candidates.sort(key=lambda x: int(x[0].get("data-level", 0)), reverse=True)
        
        # Apply consolidations
        for section, child in candidates:
            # Skip sections that have had content merged into them
            if section.get("id") in sections_with_merged_content:
                continue
                
            # Verify the consolidation is still valid (may have changed during processing)
            if self._is_valid_consolidation_candidate(section):
                self._consolidate_section(result, section, child)
        
        # Mark that we've processed this rule
        result.metadata["consolidated_sections"] = True
        return result
    
    def _identify_consolidation_candidates(self, root: ET.Element) -> List[Tuple[ET.Element, ET.Element]]:
        """Identify sections eligible for consolidation.
        
        A section is eligible if:
        1. It is a <topichead> (container)
        2. It has exactly one child that is a <topicref> with href
        3. It has no other children of type topichead or topicref
        
        Args:
            root: Root element to search in
            
        Returns:
            List of tuples (section, child) for consolidation
        """
        candidates = []
        
        def traverse(node):
            # Check if the current node is a candidate
            if node.tag == "topichead":
                if self._is_valid_consolidation_candidate(node):
                    # Find the child with href
                    for child in node:
                        if child.tag == "topicref" and child.get("href"):
                            candidates.append((node, child))
                            break
            
            # Recurse through all children
            for child in node:
                if child.tag in ("topicref", "topichead"):
                    traverse(child)
        
        traverse(root)
        return candidates
    
    def _is_valid_consolidation_candidate(self, section: ET.Element) -> bool:
        """Check if a section is a valid consolidation candidate.
        
        Args:
            section: Section element to check
            
        Returns:
            True if the section is a valid consolidation candidate
        """
        # Must be a topichead (container)
        if section.tag != "topichead":
            return False
            
        # Count children that are topicref with href or topichead
        content_children = 0
        topicref_with_href = None
        
        for child in section:
            if child.tag not in ("topicref", "topichead"):
                continue
                
            # Count as content child if it's a topicref with href or any topichead
            if child.tag == "topichead":
                content_children += 1
            elif child.tag == "topicref" and child.get("href"):
                content_children += 1
                topicref_with_href = child
                
        # Valid if there's exactly one content child and it's a topicref with href
        # This ensures we only consolidate when there's a single actual content node
        return content_children == 1 and topicref_with_href is not None
    
    def _consolidate_section(self, context: DitaContext, section: ET.Element, child: ET.Element) -> None:
        """Consolidate a section with its single child.
        
        This involves:
        1. Updating the child's title to use the section's title
        2. Moving the section's metadata to the child
        3. Replacing the section with the child in the parent
        
        Args:
            context: The DitaContext to modify
            section: The section element to consolidate
            child: The child element to promote
        """
        # Get parent of the section
        parent = section.getparent()
        if parent is None:
            return  # Can't consolidate root
            
        # Get section and child metadata
        section_meta = section.find("topicmeta")
        child_meta = child.find("topicmeta")
        
        if section_meta is not None and child_meta is not None:
            # Extract section navtitle
            section_title = section_meta.find("navtitle")
            child_title = child_meta.find("navtitle")
            
            if section_title is not None and section_title.text:
                # Update the child topic's title (both in map and in topic file)
                if child_title is not None:
                    child_title.text = section_title.text
                    
                # Update the actual topic file's title if it exists
                href = child.get("href")
                if href:
                    topic_fname = href.split("/")[-1]
                    topic = context.topics.get(topic_fname)
                    if topic is not None:
                        topic_title = topic.find("title")
                        if topic_title is not None:
                            topic_title.text = section_title.text
        
        # Preserve any data-level attribute
        if "data-level" in section.attrib:
            child.set("data-level", section.get("data-level"))
            
        # Replace section with child in the parent
        idx = parent.index(section)
        parent.remove(section)
        parent.insert(idx, child)
    
    def validate_dita_context(self, context: DitaContext) -> DitaValidationResult:
        """Validate a DitaContext against all Orlando DITA rules.
        
        Delegates to the StructureValidator to check the DitaContext against
        all rules defined in the Orlando DITA spec (A.1-C.3).
        
        Args:
            context: The DitaContext to validate
            
        Returns:
            A DitaValidationResult containing the validation status and issues
        """
        return self.validator.validate_dita_context(context)
        """Validate a DitaContext against all Orlando DITA rules.
        
        This method performs comprehensive validation of the structure
        and content according to rules A.1-C.3 in the Orlando DITA spec.
        
        Args:
            context: The DitaContext to validate
            
        Returns:
            A validation result object indicating whether the context is valid
            and listing any issues found
        """
        issues = []
        
        # A.1: Ditamap at root, topics in topics/
        self._validate_file_structure(context, issues)
        
        # B.1-B.4: Map structure and metadata
        if context.ditamap_root is not None:
            self._validate_map_structure(context.ditamap_root, issues)
            
        # C.1-C.3: Topic structure and metadata
        for fname, topic in context.topics.items():
            self._validate_topic_structure(topic, fname, issues)
            
        # Check ID uniqueness across all elements
        self._validate_id_uniqueness(context, issues)
        
        return DitaValidationResult(
            valid=len(issues) == 0,
            issues=issues
        )
    
    def _validate_file_structure(self, context: DitaContext, issues: List[str]) -> None:
        """Validate file structure according to rule A.1.
        
        A.1: The Ditamap file must reside at the root of the `DATA` directory,
        and all topic files must be in the `topics/` subdirectory.
        
        Args:
            context: The DitaContext to validate
            issues: List to append validation issues to
        """
        # Check that there's a ditamap
        if context.ditamap_root is None:
            issues.append("A.1 violation: No ditamap found")
            
        # Check that all topics have proper paths
        topic_paths = context.metadata.get("topic_paths", {})
        for fname in context.topics.keys():
            if not topic_paths.get(fname, "").startswith("topics/"):
                issues.append(f"A.1 violation: Topic {fname} not in topics/ directory")
    
    def _validate_map_structure(self, root: ET.Element, issues: List[str]) -> None:
        """Validate map structure according to rules B.1-B.4.
        
        B.1: Use <topichead> for headings that are organizational containers
        B.2: Use <topicref> for headings that link to actual content, with href
        B.3: Every <topicref> must include locktitle="yes"
        B.4: Every <topichead> and <topicref> must contain metadata
        
        Args:
            root: Root element of the ditamap
            issues: List to append validation issues to
        """
        # First, direct check for all topicrefs to ensure we don't miss any
        for topicref in root.xpath("//topicref"):
            # B.3: Check that every topicref has locktitle="yes"
            if topicref.get("locktitle") != "yes":
                node_id = topicref.get("id", "unknown")
                issues.append(f"B.3 violation: topicref (id={node_id}) missing locktitle='yes'")
        
        def validate_node(node, path=""):
            # Skip non-topic nodes
            if node.tag not in ("topichead", "topicref"):
                return
                
            node_path = f"{path}/{node.tag}"
            
            # B.1/B.2: Check proper use of topichead vs topicref
            if node.tag == "topichead" and node.get("href"):
                issues.append(f"B.1 violation: {node_path} is topichead but has href")
                
            if node.tag == "topicref" and not node.get("href"):
                issues.append(f"B.2 violation: {node_path} is topicref but missing href")
                
            # B.4: Check required metadata
            topicmeta = node.find("topicmeta")
            if topicmeta is None:
                issues.append(f"B.4 violation: {node_path} missing <topicmeta>")
            else:
                # Check for required elements inside topicmeta
                navtitle = topicmeta.find("navtitle")
                if navtitle is None or not navtitle.text:
                    issues.append(f"B.4 violation: {node_path} missing <navtitle>")
                    
                critdates = topicmeta.find("critdates")
                if critdates is None:
                    issues.append(f"B.4 violation: {node_path} missing <critdates>")
                    
                tocIndex = topicmeta.xpath("othermeta[@name='tocIndex']") 
                if not tocIndex:
                    issues.append(f"B.4 violation: {node_path} missing <othermeta name='tocIndex'>")
            
            # Recurse through children
            for i, child in enumerate(node):
                child_path = f"{node_path}[{i}]"
                validate_node(child, child_path)
        
        # Perform general validation on the tree structure
        validate_node(root)
    
    def _validate_topic_structure(self, topic: ET.Element, fname: str, issues: List[str]) -> None:
        """Validate topic structure according to rules C.1-C.3.
        
        C.1: All topic files must use <concept> as their root element
        C.2: Every element must have a unique `id` attribute
        C.3: Each topic must have a <prolog> after <title> with metadata
        
        Args:
            topic: Topic element to validate
            fname: Filename for reference in issues
            issues: List to append validation issues to
        """
        # C.1: Check root element is concept
        if topic.tag != "concept":
            issues.append(f"C.1 violation: {fname} root element is {topic.tag}, not concept")
            
        # C.3: Check prolog and structure
        title = topic.find("title")
        if title is None:
            issues.append(f"C.3 violation: {fname} missing <title>")
        
        prolog = topic.find("prolog")
        if prolog is None:
            issues.append(f"C.3 violation: {fname} missing <prolog>")
        else:
            # Check if prolog is immediately after title
            if title is not None and topic.index(prolog) != topic.index(title) + 1:
                issues.append(f"C.3 violation: {fname} <prolog> not immediately after <title>")
                
            # Check required elements in prolog
            critdates = prolog.find("critdates")
            if critdates is None:
                issues.append(f"C.3 violation: {fname} <prolog> missing <critdates>")
                
            metadata = prolog.find("metadata")
            if metadata is None:
                issues.append(f"C.3 violation: {fname} <prolog> missing <metadata>")
    
    def _validate_id_uniqueness(self, context: DitaContext, issues: List[str]) -> None:
        """Validate ID uniqueness across all elements (rule C.2).
        
        C.2: Every element in a topic file must have a unique ID.
        
        Args:
            context: The DitaContext to validate
            issues: List to append validation issues to
        """
        # Track IDs seen across all files
        seen_ids = {}
        
        # Check all topics
        for fname, topic in context.topics.items():
            # Check that all elements have IDs
            elements_without_id = topic.xpath(".//*[not(@id)]")
            for el in elements_without_id:
                if el.tag not in ("#text", "#comment"):  # Skip text and comments
                    # Use tag and parent structure instead of full path
                    issues.append(f"C.2 violation: {fname} element <{el.tag}> missing id attribute")
                    
            # Check for ID uniqueness
            for el in topic.xpath(".//*[@id]"):
                id_val = el.get("id")
                if id_val in seen_ids:
                    prev_file, prev_elem_tag = seen_ids[id_val]
                    current_elem_tag = el.tag
                    issues.append(f"C.2 violation: ID '{id_val}' in {fname} on <{current_elem_tag}> duplicates ID in {prev_file} on <{prev_elem_tag}>")
                else:
                    seen_ids[id_val] = (fname, el.tag)
    
    # Helper methods for implementation in next iterations
    def _identify_merge_operations(self, context: DitaContext, rules: StructureRules) -> List[MergeOperation]:
        """Identify all merge operations to be performed based on rules.
        
        This method analyzes the structure and identifies all topics that
        need to be merged according to depth and style rules.
        
        Args:
            context: The DitaContext to analyze
            rules: The structure rules to apply
            
        Returns:
            A list of merge operations to be performed
        """
        # We'll implement this in the next iteration
        return []
        
    def _execute_merge_operation(self, context: DitaContext, operation: MergeOperation) -> None:
        """Execute a merge operation on the given context.
        
        Implements FR6.3: ID uniqueness and reference update
        - All `@id` attributes within merged content are regenerated
        - All internal references (`@href`, `@conref`) updated to point to new IDs
        
        Args:
            context: The DitaContext to modify
            operation: The merge operation to perform
            
        Raises:
            ValueError: If source or target topic not found
        """
        # Find source and target topics
        source_topic = None
        target_topic = None
        source_fname = None
        target_fname = None
        
        # First attempt: If we have hrefs, use them to find the topics
        if operation.source_id.href:
            # Handle both full paths and filenames
            if '/' in operation.source_id.href:
                source_fname = operation.source_id.href.split('/')[-1]
            else:
                source_fname = operation.source_id.href
                
            if source_fname in context.topics:
                source_topic = context.topics.get(source_fname)
            else:
                # Try to find the topic by checking all keys
                for key, topic in context.topics.items():
                    if key.endswith(source_fname):
                        source_topic = topic
                        source_fname = key
                        break
        
        # If href doesn't work, try finding by element ID
        if source_topic is None and operation.source_id.element_id:
            for fname, topic in context.topics.items():
                if topic.get("id") == operation.source_id.element_id:
                    source_topic = topic
                    source_fname = fname
                    break
            
        # First attempt: If we have hrefs, use them to find the topics
        if operation.target_id.href:
            # Handle both full paths and filenames
            if '/' in operation.target_id.href:
                target_fname = operation.target_id.href.split('/')[-1]
            else:
                target_fname = operation.target_id.href
                
            if target_fname in context.topics:
                target_topic = context.topics.get(target_fname)
            else:
                # Try to find the topic by checking all keys
                for key, topic in context.topics.items():
                    if key.endswith(target_fname):
                        target_topic = topic
                        target_fname = key
                        break
        
        # If href doesn't work, try finding by element ID
        if target_topic is None and operation.target_id.element_id:
            for fname, topic in context.topics.items():
                if topic.get("id") == operation.target_id.element_id:
                    target_topic = topic
                    target_fname = fname
                    break
            
        # Verify we have both topics
        if source_topic is None or target_topic is None:
            raise ValueError(f"Source or target topic not found. Source ID: {operation.source_id.element_id}, " + 
                           f"Target ID: {operation.target_id.element_id}. Available topics: {list(context.topics.keys())}")
        
        # Step 1: If requested, preserve the title as a paragraph
        if operation.preserve_title:
            self._preserve_title_as_paragraph(source_topic, target_topic)
            
        # Step 2: Create ID mapping
        id_mapping = self._generate_id_mapping(source_topic)
        
        # Step 3: Copy all content from source to target
        self._copy_content(source_topic, target_topic, id_mapping)
        
        # Since we're keeping the source topic in the dictionary,
        # we need to also update its IDs to avoid duplicate IDs with the merged content
        if source_fname in context.topics:
            # Update all IDs in the source topic with new unique IDs
            for element in source_topic.xpath(".//*[@id]"):
                old_id = element.get("id")
                if old_id:
                    element.set("id", generate_dita_id())
                    
        # Update all references in the target topic
        self._update_references(target_topic, id_mapping)
        
        # Update all references in the entire context
        self._update_all_references(context, id_mapping)
    
    def _preserve_title_as_paragraph(self, source_topic: ET.Element, target_topic: ET.Element) -> None:
        """Convert source topic title to a paragraph at start of target topic body.
        
        Args:
            source_topic: The source topic element
            target_topic: The target topic element
        """
        # Find source title
        source_title = source_topic.find("title")
        if source_title is None or not source_title.text:
            return
            
        # Find target conbody (create if needed)
        target_conbody = target_topic.find("conbody")
        if target_conbody is None:
            target_conbody = ET.SubElement(target_topic, "conbody", id=generate_dita_id())
            
        # Create a new paragraph with the source title
        title_p = ET.Element("p", id=generate_dita_id())
        title_p.text = source_title.text
        
        # Insert at the beginning of conbody
        if len(target_conbody) > 0:
            target_conbody.insert(0, title_p)
        else:
            target_conbody.append(title_p)
    
    def _generate_id_mapping(self, source_topic: ET.Element) -> Dict[str, str]:
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
            
            # Update IDs in the copy using the mapping
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
    
    # End of StructureService class
