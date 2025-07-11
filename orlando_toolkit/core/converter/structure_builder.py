from __future__ import annotations

"""Document structure analysis for two-pass DITA conversion.

This module builds a hierarchical representation of the document structure,
allowing for deferred section vs module decisions based on complete context.
"""

from typing import List
from docx import Document  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore
from docx.table import Table  # type: ignore

from orlando_toolkit.core.models import HeadingNode
from orlando_toolkit.core.parser import iter_block_items
from orlando_toolkit.core.converter.helpers import get_heading_level

import uuid
import os
from datetime import datetime
from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import generate_dita_id, normalize_topic_title
from orlando_toolkit.core.generators import create_dita_table
from orlando_toolkit.core.converter.helpers import (
    create_dita_concept,
    process_paragraph_content_and_images,
    apply_paragraph_formatting
)


def build_document_structure(doc: Document, style_heading_map: dict, all_images_map_rid: dict) -> List[HeadingNode]:
    """Build hierarchical document structure from Word document.
    
    First pass of two-pass conversion: analyze complete document structure
    without making immediate section vs module decisions.
    
    Parameters
    ----------
    doc
        Word document to analyze
    style_heading_map
        Mapping of style names to heading levels
    all_images_map_rid
        Image relationship ID mapping for content processing
        
    Returns
    -------
    List[HeadingNode]
        Root-level heading nodes with complete hierarchy
    """
    root_nodes: List[HeadingNode] = []
    heading_stack: List[HeadingNode] = []  # Track parent chain for hierarchy
    
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            heading_level = get_heading_level(block, style_heading_map)
            
            if heading_level is not None:
                # Create new heading node
                text = block.text.strip()
                if not text:
                    continue  # Skip empty headings
                    
                style_name = getattr(block.style, 'name', None) if block.style else None
                node = HeadingNode(
                    text=text,
                    level=heading_level,
                    style_name=style_name
                )
                
                # Find correct parent in hierarchy
                # Remove nodes from stack that are at same or deeper level
                while heading_stack and heading_stack[-1].level >= heading_level:
                    heading_stack.pop()
                
                # Add to hierarchy
                if heading_stack:
                    # Has parent - add as child
                    parent = heading_stack[-1]
                    parent.add_child(node)
                else:
                    # No parent - add as root node
                    root_nodes.append(node)
                
                # Add to stack for potential children
                heading_stack.append(node)
            else:
                # Content block - add to current heading if exists
                if heading_stack:
                    current_heading = heading_stack[-1]
                    current_heading.add_content_block(block)
                # Note: Content before first heading is ignored (matches current behavior)
                
        elif isinstance(block, Table):
            # Table block - add to current heading if exists
            if heading_stack:
                current_heading = heading_stack[-1]
                current_heading.add_content_block(block)
    
    return root_nodes


def determine_node_roles(nodes: List[HeadingNode]) -> None:
    """Determine section vs module roles for all nodes in hierarchy.
    
    Decision logic:
    - Has children → Section
    - No children → Module
    - Section with content → Create implicit module child for content
    
    Parameters
    ----------
    nodes
        List of heading nodes to process (modified in-place)
    """
    for node in nodes:
        if node.has_children():
            node.role = "section"
            # If section has content, it will be handled during DITA generation
            # by creating an implicit module child
        else:
            node.role = "module"
        
        # Recursively process children
        determine_node_roles(node.children)


def generate_dita_from_structure(
    nodes: List[HeadingNode], 
    context: DitaContext, 
    metadata: dict,
    all_images_map_rid: dict,
    parent_element: ET.Element,
    heading_counters: list,
    parent_elements: dict
) -> None:
    """Generate DITA topics and map structure from hierarchical document structure.
    
    Second pass of two-pass conversion: create DITA topics with correct
    section vs module roles based on analyzed structure.
    
    Parameters
    ----------
    nodes
        List of heading nodes to process
    context
        DITA context to populate with topics
    metadata
        Document metadata
    all_images_map_rid
        Image relationship ID mapping
    parent_element
        Parent element in ditamap for topicref creation
    heading_counters
        Heading counters for TOC indexing
    parent_elements
        Parent elements mapping for hierarchy
    """
    for node in nodes:
        level = node.level
        
        # Update heading counters
        if level > len(heading_counters):
            heading_counters.extend([0] * (level - len(heading_counters)))
        heading_counters[level - 1] += 1
        for i in range(level, len(heading_counters)):
            heading_counters[i] = 0
        toc_index = ".".join(str(c) for c in heading_counters[:level] if c > 0)
        
        # Generate unique file name and topic ID
        file_name = f"topic_{uuid.uuid4().hex[:10]}.dita"
        topic_id = file_name.replace(".dita", "")
        
        if node.role == "section":
            # Create section as pure structural topichead (no topic file)
            topichead = ET.SubElement(
                parent_element,
                "topichead",
                {"locktitle": "yes"},
            )
            topichead.set("data-level", str(level))
            
            # Add topicmeta for section
            topicmeta_ref = ET.SubElement(topichead, "topicmeta")
            navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
            navtitle_ref.text = normalize_topic_title(node.text)
            critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
            ET.SubElement(critdates_ref, "created", date=metadata.get("revision_date"))
            ET.SubElement(critdates_ref, "revised", modified=metadata.get("revision_date"))
            ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content=toc_index)
            ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
            ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")
            
            # Preserve style information
            if node.style_name:
                topichead.set("data-style", node.style_name)
            
            # Note: No topic file created for sections
            parent_elements[level] = topichead
            
            # If section has content, create a content module child for it
            if node.has_content():
                module_file = f"topic_{uuid.uuid4().hex[:10]}.dita"
                module_id = module_file.replace(".dita", "")
                
                module_concept, module_conbody = create_dita_concept(
                    normalize_topic_title(node.text),  # Same title as section
                    module_id,
                    metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
                )
                
                # Add content to module
                _add_content_to_topic(module_conbody, node.content_blocks, all_images_map_rid)
                
                # Create module topicref as child of section topichead
                module_topicref = ET.SubElement(
                    topichead,
                    "topicref",
                    {"href": f"topics/{module_file}", "locktitle": "yes"},
                )
                
                tm = ET.SubElement(module_topicref, "topicmeta")
                nt = ET.SubElement(tm, "navtitle")
                nt.text = normalize_topic_title(node.text)
                
                context.topics[module_file] = module_concept
            
            # Process children recursively
            generate_dita_from_structure(
                node.children, context, metadata, all_images_map_rid,
                topichead, heading_counters, parent_elements
            )
            
        else:  # node.role == "module"
            # Create module topic with content
            module_concept, module_conbody = create_dita_concept(
                normalize_topic_title(node.text),
                topic_id,
                metadata.get("revision_date", datetime.now().strftime("%Y-%m-%d")),
            )
            
            # Add content to module
            _add_content_to_topic(module_conbody, node.content_blocks, all_images_map_rid)
            
            # Create topicref in ditamap
            topicref = ET.SubElement(
                parent_element,
                "topicref",
                {"href": f"topics/{file_name}", "locktitle": "yes"},
            )
            topicref.set("data-level", str(level))
            
            # Add topicmeta
            topicmeta_ref = ET.SubElement(topicref, "topicmeta")
            navtitle_ref = ET.SubElement(topicmeta_ref, "navtitle")
            navtitle_ref.text = normalize_topic_title(node.text)
            critdates_ref = ET.SubElement(topicmeta_ref, "critdates")
            ET.SubElement(critdates_ref, "created", date=metadata.get("revision_date"))
            ET.SubElement(critdates_ref, "revised", modified=metadata.get("revision_date"))
            ET.SubElement(topicmeta_ref, "othermeta", name="tocIndex", content=toc_index)
            ET.SubElement(topicmeta_ref, "othermeta", name="foldout", content="false")
            ET.SubElement(topicmeta_ref, "othermeta", name="tdm", content="false")
            
            # Preserve style information
            if node.style_name:
                topicref.set("data-style", node.style_name)
            
            # Store in context
            context.topics[file_name] = module_concept
            parent_elements[level] = topicref
            
            # Process children recursively (modules can have children too)
            generate_dita_from_structure(
                node.children, context, metadata, all_images_map_rid,
                topicref, heading_counters, parent_elements
            )


def _add_content_to_topic(conbody: ET.Element, content_blocks: List, all_images_map_rid: dict) -> None:
    """Add content blocks to a topic's conbody element.
    
    Parameters
    ----------
    conbody
        The conbody element to add content to
    content_blocks
        List of content blocks (paragraphs, tables, etc.)
    all_images_map_rid
        Image relationship ID mapping
    """
    current_list = None
    current_sl = None
    
    for block in content_blocks:
        if isinstance(block, Table):
            current_list = None
            current_sl = None
            
            p_for_table = ET.SubElement(conbody, "p", id=generate_dita_id())
            dita_table = create_dita_table(block, all_images_map_rid)
            p_for_table.append(dita_table)
            
        elif isinstance(block, Paragraph):
            # Check if it's a list item
            is_list_item = (
                block._p.pPr is not None and block._p.pPr.numPr is not None
            )
            
            text = block.text.strip()
            is_image_para = any(run.element.xpath(".//@r:embed") for run in block.runs) and not text
            
            if is_image_para:
                current_list = None
                if current_sl is None:
                    current_sl = ET.SubElement(conbody, "sl", id=generate_dita_id())
                sli = ET.SubElement(current_sl, "sli", id=generate_dita_id())
                for run in block.runs:
                    r_ids = run.element.xpath(".//@r:embed")
                    if r_ids and r_ids[0] in all_images_map_rid:
                        img_filename = os.path.basename(all_images_map_rid[r_ids[0]])
                        ET.SubElement(sli, "image", href=f"../media/{img_filename}", id=generate_dita_id())
                        break
            elif is_list_item:
                current_sl = None
                list_style = "ul"
                if current_list is None or current_list.tag != list_style:
                    current_list = ET.SubElement(conbody, list_style, id=generate_dita_id())
                li = ET.SubElement(current_list, "li", id=generate_dita_id())
                p_in_li = ET.SubElement(li, "p", id=generate_dita_id())
                process_paragraph_content_and_images(p_in_li, block, all_images_map_rid, None)
            else:
                current_list = None
                current_sl = None
                if not text:
                    continue
                p_el = ET.SubElement(conbody, "p", id=generate_dita_id())
                apply_paragraph_formatting(p_el, block)
                process_paragraph_content_and_images(p_el, block, all_images_map_rid, conbody) 