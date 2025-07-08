# -*- coding: utf-8 -*-
"""Domain models for DITA structure operations.

This module defines the domain models used by the structure services.
These models encapsulate business concepts and rules as immutable data structures.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Union
from lxml import etree as ET  # type: ignore
from uuid import uuid4


class ElementType(Enum):
    """Enumeration of DITA element types relevant to structure operations."""
    TOPIC_HEAD = auto()  # <topichead> - container without content
    TOPIC_REF = auto()   # <topicref> - link to actual content
    TOPIC = auto()       # <concept> - actual topic content
    UNKNOWN = auto()     # Any other element


@dataclass(frozen=True)
class TopicIdentifier:
    """Uniquely identifies a topic or section in the ditamap.
    
    Attributes:
        element_id: XML ID of the element if available, otherwise generated UUID
        href: Path to topic file if this is a topicref with href
        title: Title text for display/debug purposes
    """
    element_id: str
    href: Optional[str] = None
    title: str = "Untitled"
    
    @classmethod
    def from_element(cls, element: ET.Element) -> TopicIdentifier:
        """Create a TopicIdentifier from an XML element.
        
        Args:
            element: XML element (topichead, topicref, or concept)
            
        Returns:
            A new TopicIdentifier instance
        """
        element_id = element.get("id", str(uuid4()))
        href = element.get("href") if element.tag == "topicref" else None
        
        # Extract title from different possible locations
        title = "Untitled"
        if element.tag in ("topichead", "topicref"):
            navtitle = element.find("topicmeta/navtitle")
            if navtitle is not None and navtitle.text:
                title = navtitle.text
        elif element.tag == "concept":
            title_el = element.find("title")
            if title_el is not None and title_el.text:
                title = title_el.text
                
        return cls(element_id=element_id, href=href, title=title)


@dataclass
class StructureRules:
    """Configuration for DITA structure operations.
    
    This is the primary input model for structure operations, defining how
    merging and consolidation should be performed.
    
    Attributes:
        max_depth: Maximum heading level that starts a new topic (FR6.1)
                  Headings deeper than this will be merged into parent topics.
        excluded_styles: Dictionary mapping heading levels to sets of style names
                        that should be merged rather than treated as separate topics.
        consolidate_sections: If True, apply the consolidation rule (FR6.4) after merging.
    """
    max_depth: int = 3
    excluded_styles: Dict[int, Set[str]] = field(default_factory=dict)
    consolidate_sections: bool = True


@dataclass
class MergeOperation:
    """Represents a merge operation to be performed on the structure.
    
    This model encapsulates all details of a merge operation, whether it's
    triggered by depth rules, style rules, or manual selection.
    
    Attributes:
        source_id: The identifier of the source topic to merge
        target_id: The identifier of the target topic to merge into
        reason: The reason for this merge (depth, style, manual)
        preserve_title: Whether to preserve the source topic's title as a paragraph
    """
    source_id: TopicIdentifier
    target_id: TopicIdentifier
    reason: str
    preserve_title: bool = True


@dataclass
class DitaValidationResult:
    """Result of validating a DitaContext against Orlando DITA rules.
    
    Attributes:
        valid: Whether the DitaContext is valid according to all rules
        issues: List of validation issues found (empty if valid)
    """
    valid: bool = True
    issues: List[str] = field(default_factory=list)
