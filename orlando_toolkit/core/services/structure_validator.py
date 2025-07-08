# -*- coding: utf-8 -*-
"""Validation service for DITA structure compliance.

This module provides a service for validating DITA contexts against Orlando DITA rules.
It focuses on structure validation, ensuring proper hierarchy, element composition,
and compliance with all Orlando DITA rules (A.1-C.3).
"""

from __future__ import annotations
from typing import List, Set, TYPE_CHECKING
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.services.structure_models import DitaValidationResult

if TYPE_CHECKING:
    from orlando_toolkit.core.models import DitaContext


class StructureValidator:
    """Service for validating DITA structures against Orlando DITA rules.
    
    This service is responsible for validating DITA contexts against all
    Orlando DITA rules (A.1-C.3) to ensure compliance.
    """
    
    def validate_dita_context(self, context: DitaContext) -> DitaValidationResult:
        """Validate a DitaContext against all Orlando DITA rules.
        
        This method checks the DitaContext against all rules defined in the
        Orlando DITA spec (A.1-C.3) and returns a validation result.
        
        Args:
            context: The DitaContext to validate
            
        Returns:
            A DitaValidationResult containing the validation status and issues
        """
        result = DitaValidationResult()
        
        # Validate all rules
        self._validate_file_structure(context, result)
        self._validate_ditamap_structure(context, result)
        self._validate_topic_structure(context, result)
        self._validate_id_uniqueness(context, result)
        
        return result
    
    def _validate_file_structure(self, context: DitaContext, result: DitaValidationResult) -> None:
        """Validate Orlando rule A.1: File structure.
        
        A.1: The Ditamap file must reside at the root of the DATA directory, and 
        all topic files must be in the topics/ subdirectory.
        
        Args:
            context: The DitaContext to validate
            result: The validation result to update
        """
        # Check if topic paths are in metadata
        if "topic_paths" not in context.metadata:
            result.valid = False
            result.issues.append("Missing topic_paths in metadata (Rule A.1)")
            return
            
        # Check that all topic paths are in the topics/ directory
        topic_paths = context.metadata["topic_paths"]
        for fname, path in topic_paths.items():
            if not path.startswith("topics/"):
                result.valid = False
                result.issues.append(f"Topic {fname} path '{path}' not in topics/ directory (Rule A.1)")
    
    def _validate_ditamap_structure(self, context: DitaContext, result: DitaValidationResult) -> None:
        """Validate Orlando rules B.1-B.4: Ditamap structure.
        
        B.1: Use <topichead> for headings that are organizational containers without content
        B.2: Use <topicref> for headings that link to actual content, with href to the topic file
        B.3: Every <topicref> must include locktitle="yes"
        B.4: Every <topichead> and <topicref> must contain <topicmeta> with <navtitle>, 
            <critdates>, and <othermeta name="tocIndex" ...>
            
        Args:
            context: The DitaContext to validate
            result: The validation result to update
        """
        # Check for root ditamap
        if context.ditamap_root is None:
            result.valid = False
            result.issues.append("Missing ditamap root (Rules B.1-B.4)")
            return
            
        # Process all topichead and topicref elements
        for element in context.ditamap_root.xpath(".//*[local-name()='topichead' or local-name()='topicref']"):
            # Check B.1 & B.2: topichead vs topicref usage
            if element.tag == "topichead" and element.get("href"):
                result.valid = False
                result.issues.append(f"topichead element with href='{element.get('href')}' should be topicref (Rule B.1)")
                
            if element.tag == "topicref" and not element.get("href"):
                result.valid = False
                result.issues.append("topicref element without href should be topichead (Rule B.2)")
                
            # Check B.3: locktitle on topicref
            if element.tag == "topicref" and element.get("locktitle") != "yes":
                result.valid = False
                result.issues.append(f"topicref missing locktitle='yes' (Rule B.3)")
                
            # Check B.4: Required metadata
            topicmeta = element.find("topicmeta")
            if topicmeta is None:
                result.valid = False
                result.issues.append(f"Missing topicmeta in {element.tag} (Rule B.4)")
                continue
                
            navtitle = topicmeta.find("navtitle")
            if navtitle is None:
                result.valid = False
                result.issues.append(f"Missing navtitle in {element.tag}/topicmeta (Rule B.4)")
                
            critdates = topicmeta.find("critdates")
            if critdates is None:
                result.valid = False
                result.issues.append(f"Missing critdates in {element.tag}/topicmeta (Rule B.4)")
                
            othermeta = topicmeta.find("othermeta[@name='tocIndex']")
            if othermeta is None:
                result.valid = False
                result.issues.append(f"Missing othermeta name='tocIndex' in {element.tag}/topicmeta (Rule B.4)")
    
    def _validate_topic_structure(self, context: DitaContext, result: DitaValidationResult) -> None:
        """Validate Orlando rules C.1-C.3: Topic structure.
        
        C.1: All topic files must use <concept> as their root element
        C.2: Every element in a topic file must have a unique id attribute
        C.3: Each topic must have a <prolog> element immediately after the <title>,
            containing <critdates> and <metadata>
            
        Args:
            context: The DitaContext to validate
            result: The validation result to update
        """
        # Check each topic
        for fname, topic in context.topics.items():
            # C.1: Root element must be concept
            if topic.tag != "concept":
                result.valid = False
                result.issues.append(f"Topic {fname} root element is '{topic.tag}', should be 'concept' (Rule C.1)")
                
            # C.3: Prolog after title
            title = topic.find("title")
            if title is None:
                result.valid = False
                result.issues.append(f"Topic {fname} missing title element (Rule C.3)")
            else:
                # Check if the next element after title is prolog
                title_idx = list(topic).index(title)
                if len(list(topic)) <= title_idx + 1 or list(topic)[title_idx + 1].tag != "prolog":
                    result.valid = False
                    result.issues.append(f"Topic {fname} prolog not immediately after title (Rule C.3)")
                else:
                    prolog = list(topic)[title_idx + 1]
                    # Check prolog contents
                    critdates = prolog.find("critdates")
                    if critdates is None:
                        result.valid = False
                        result.issues.append(f"Topic {fname} missing critdates in prolog (Rule C.3)")
                        
                    metadata = prolog.find("metadata")
                    if metadata is None:
                        result.valid = False
                        result.issues.append(f"Topic {fname} missing metadata in prolog (Rule C.3)")
    
    def _validate_id_uniqueness(self, context: DitaContext, result: DitaValidationResult) -> None:
        """Validate Orlando rule C.2: ID uniqueness.
        
        C.2: Every element in a topic file must have a unique id attribute
        
        Args:
            context: The DitaContext to validate
            result: The validation result to update
        """
        # Track all IDs across the context
        all_ids: Set[str] = set()
        duplicate_ids: Set[str] = set()
        
        # Check each topic
        for fname, topic in context.topics.items():
            # Check all elements with id attributes
            for element in topic.xpath(".//*[@id]"):
                element_id = element.get("id")
                if element_id in all_ids:
                    duplicate_ids.add(element_id)
                else:
                    all_ids.add(element_id)
        
        # Report any duplicates
        if duplicate_ids:
            result.valid = False
            for dup_id in duplicate_ids:
                result.issues.append(f"Duplicate ID '{dup_id}' found (Rule C.2)")
                
        # Check that all elements have IDs
        for fname, topic in context.topics.items():
            # Get a list of elements without IDs (excluding text nodes)
            missing_ids = [element.tag for element in topic.xpath(".//*[not(@id) and not(self::text())]")]
            
            if missing_ids:
                result.valid = False
                result.issues.append(f"Topic {fname} has {len(missing_ids)} elements without IDs: {', '.join(missing_ids)} (Rule C.2)")
