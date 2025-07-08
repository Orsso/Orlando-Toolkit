import unittest
from lxml import etree
import os
import sys
import uuid
from copy import deepcopy

# Add the parent directory to the sys.path to be able to import the modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from orlando_toolkit.core.merge import (
    consolidate_sections,
    merge_topics_below_depth,
    merge_topics_by_styles,
    generate_dita_id,
    _new_topic_with_title,
    _copy_content,
    _ensure_content_module
)
from orlando_toolkit.core.models import DitaContext

class TestMergeFunctions(unittest.TestCase):
    """Test cases for the merge functions in core/merge.py."""
    
    def setUp(self):
        """Set up a test context with a simple DITA map and topics."""
        # Create a basic DitaContext with a simple map structure
        self.ctx = DitaContext()
        
        # Create a simple map structure for testing
        self.ctx.ditamap_root = etree.Element("map")
        
        # Dictionary to hold topics
        self.ctx.topics = {}
        
        # Metadata dictionary
        self.ctx.metadata = {}
        
        # Track original test IDs to avoid collisions in ID generation
        self.orig_generate_id = generate_dita_id
    
    def tearDown(self):
        """Clean up after test."""
        # Restore original ID generation function
        globals()['generate_dita_id'] = self.orig_generate_id
    
    def create_test_map_for_consolidation(self):
        """Create a test map structure with sections and content modules for consolidation testing."""
        # Override ID generation to be deterministic for testing
        id_counter = 0
        def mock_generate_id():
            nonlocal id_counter
            id_counter += 1
            return f"test_id_{id_counter}"
        
        globals()['generate_dita_id'] = mock_generate_id
        
        # Create root map
        root = self.ctx.ditamap_root
        
        # Create topics and topic refs
        
        # Level 1 Section (should not be consolidated as it has multiple children)
        section1 = etree.SubElement(root, "topicref")
        section1_meta = etree.SubElement(section1, "topicmeta")
        section1_navtitle = etree.SubElement(section1_meta, "navtitle")
        section1_navtitle.text = "Section 1"
        
        # Content Module 1 under Section 1
        topic1_id = "topic_1"
        topic1_fname = f"{topic1_id}.dita"
        topic1_ref = etree.SubElement(section1, "topicref", href=f"topics/{topic1_fname}")
        topic1 = _new_topic_with_title("Content 1")
        self.ctx.topics[topic1_fname] = topic1
        
        # Level 2 Section under Section 1 (should be consolidated)
        section2 = etree.SubElement(section1, "topicref")
        section2_meta = etree.SubElement(section2, "topicmeta")
        section2_navtitle = etree.SubElement(section2_meta, "navtitle")
        section2_navtitle.text = "Section 2"
        
        # Content Module 2 under Section 2
        topic2_id = "topic_2"
        topic2_fname = f"{topic2_id}.dita"
        topic2_ref = etree.SubElement(section2, "topicref", href=f"topics/{topic2_fname}")
        topic2 = _new_topic_with_title("Content 2")
        body = etree.SubElement(topic2, "conbody")
        content_para = etree.SubElement(body, "p")
        content_para.text = "This is content from module 2"
        self.ctx.topics[topic2_fname] = topic2
        
        # Level 1 Section with nested section structure (for testing multi-level consolidation)
        section3 = etree.SubElement(root, "topicref")
        section3_meta = etree.SubElement(section3, "topicmeta")
        section3_navtitle = etree.SubElement(section3_meta, "navtitle")
        section3_navtitle.text = "Section 3"
        
        # Level 2 Subsection
        section3_1 = etree.SubElement(section3, "topicref")
        section3_1_meta = etree.SubElement(section3_1, "topicmeta")
        section3_1_navtitle = etree.SubElement(section3_1_meta, "navtitle")
        section3_1_navtitle.text = "Section 3.1"
        
        # Level 3 Subsection (will be consolidated up to Section 3.1 first, then to Section 3)
        section3_1_1 = etree.SubElement(section3_1, "topicref")
        section3_1_1_meta = etree.SubElement(section3_1_1, "topicmeta")
        section3_1_1_navtitle = etree.SubElement(section3_1_1_meta, "navtitle")
        section3_1_1_navtitle.text = "Section 3.1.1"
        
        # Content Module under deepest section
        topic3_id = "topic_3"
        topic3_fname = f"{topic3_id}.dita"
        topic3_ref = etree.SubElement(section3_1_1, "topicref", href=f"topics/{topic3_fname}")
        topic3 = _new_topic_with_title("Content 3")
        body = etree.SubElement(topic3, "conbody")
        content_para = etree.SubElement(body, "p")
        content_para.text = "This is content from module 3"
        self.ctx.topics[topic3_fname] = topic3
        
        return {
            'root': root,
            'section1': section1,
            'section2': section2,
            'section3': section3,
            'section3_1': section3_1,
            'section3_1_1': section3_1_1,
            'topic1_ref': topic1_ref,
            'topic2_ref': topic2_ref,
            'topic3_ref': topic3_ref,
        }
    
    def test_consolidate_sections_simple(self):
        """Test consolidation of a simple section with one content module."""
        # Create a simple map with one section containing one content module
        root = self.ctx.ditamap_root
        
        # Create a section
        section = etree.SubElement(root, "topicref")
        section_meta = etree.SubElement(section, "topicmeta")
        section_navtitle = etree.SubElement(section_meta, "navtitle")
        section_navtitle.text = "Test Section"
        
        # Create a content module under the section
        topic_id = "topic_test"
        topic_fname = f"{topic_id}.dita"
        topic_ref = etree.SubElement(section, "topicref", href=f"topics/{topic_fname}")
        topic = _new_topic_with_title("Test Content")
        body = etree.SubElement(topic, "body")
        content_para = etree.SubElement(body, "p")
        content_para.text = "This is test content"
        self.ctx.topics[topic_fname] = topic
        
        # Run the consolidation
        consolidate_sections(self.ctx)
        
        # Verify the section has been consolidated
        self.assertIn("href", section.attrib)
        self.assertEqual(len(section), 1)  # Only the topicmeta should remain
        
        # Verify content was preserved
        new_fname = section.get("href").split("/")[-1]
        self.assertIn(new_fname, self.ctx.topics)
        
        consolidated_topic = self.ctx.topics[new_fname]
        self.assertEqual(consolidated_topic.find("title").text, "Test Section")
        
        # Verify old topic is removed
        self.assertNotIn(topic_fname, self.ctx.topics)
    
    def test_consolidate_sections_nested(self):
        """Test consolidation of nested sections with a single content module at the deepest level."""
        # Create a test map with nested sections
        map_components = self.create_test_map_for_consolidation()
        
        # Run consolidation
        consolidate_sections(self.ctx)
        
        # Verify Section 3 was consolidated all the way up (three levels of sections into one content module)
        section3 = map_components['section3']
        self.assertIn("href", section3.attrib)
        
        # Verify content was preserved and title is from the top section
        new_fname = section3.get("href").split("/")[-1]
        consolidated_topic = self.ctx.topics[new_fname]
        self.assertEqual(consolidated_topic.find("title").text, "Section 3")
        
        # Verify there's a paragraph with the content from the deepest module
        body = consolidated_topic.find("body")
        self.assertIsNotNone(body)
        para = body.find("p")
        self.assertIsNotNone(para)
        self.assertEqual(para.text, "This is content from module 3")
        
        # Verify section 2 was also consolidated
        section2 = map_components['section2']
        self.assertIn("href", section2.attrib)
        
        # Verify section 1 was NOT consolidated as it has multiple children
        section1 = map_components['section1']
        self.assertNotIn("href", section1.attrib)
    
    def test_consolidate_sections_multiple_passes(self):
        """Test that consolidation correctly handles situations requiring multiple passes."""
        # Create a complex nested structure requiring multiple passes
        root = self.ctx.ditamap_root
        
        # Level 1 Section
        section1 = etree.SubElement(root, "topicref")
        section1_meta = etree.SubElement(section1, "topicmeta")
        section1_navtitle = etree.SubElement(section1_meta, "navtitle")
        section1_navtitle.text = "Multi-Pass Section"
        
        # Four levels of nested sections, each with a single section child
        current_section = section1
        for i in range(1, 5):
            new_section = etree.SubElement(current_section, "topicref")
            new_meta = etree.SubElement(new_section, "topicmeta")
            new_navtitle = etree.SubElement(new_meta, "navtitle")
            new_navtitle.text = f"Level {i} Section"
            current_section = new_section
        
        # Add a content module to the deepest section
        topic_id = "topic_deep"
        topic_fname = f"{topic_id}.dita"
        topic_ref = etree.SubElement(current_section, "topicref", href=f"topics/{topic_fname}")
        topic = _new_topic_with_title("Deep Content")
        body = etree.SubElement(topic, "body")
        content_para = etree.SubElement(body, "p")
        content_para.text = "This is content from the deepest module"
        self.ctx.topics[topic_fname] = topic
        
        # Run consolidation with a limited number of iterations
        self.ctx.metadata["consolidation_iterations"] = 2
        consolidate_sections(self.ctx)
        
        # Verify the top section now has an href (fully consolidated)
        self.assertIn("href", section1.attrib)
        
        # Verify content was preserved and title is from the top section
        new_fname = section1.get("href").split("/")[-1]
        consolidated_topic = self.ctx.topics[new_fname]
        self.assertEqual(consolidated_topic.find("title").text, "Multi-Pass Section")
        
        # Verify there's a paragraph with the content from the deepest module
        body = consolidated_topic.find("body")
        self.assertIsNotNone(body)
        para = body.find("p")
        self.assertIsNotNone(para)
        self.assertEqual(para.text, "This is content from the deepest module")
    
    def test_consolidate_sections_with_attributes(self):
        """Test that data-level and data-style attributes are preserved during consolidation."""
        # Create a simple map with one section containing one content module with attributes
        root = self.ctx.ditamap_root
        
        # Create a section
        section = etree.SubElement(root, "topicref")
        section_meta = etree.SubElement(section, "topicmeta")
        section_navtitle = etree.SubElement(section_meta, "navtitle")
        section_navtitle.text = "Attribute Section"
        
        # Create a content module with attributes under the section
        topic_id = "topic_attr"
        topic_fname = f"{topic_id}.dita"
        topic_ref = etree.SubElement(section, "topicref", 
                                   href=f"topics/{topic_fname}",
                                   **{"data-level": "2", "data-style": "heading"})
        topic = _new_topic_with_title("Attribute Content")
        self.ctx.topics[topic_fname] = topic
        
        # Run the consolidation
        consolidate_sections(self.ctx)
        
        # Verify attributes were preserved
        self.assertEqual(section.get("data-level"), "2")
        self.assertEqual(section.get("data-style"), "heading")
    
    def test_merge_topics_below_depth_and_consolidate(self):
        """Test the combination of merge_topics_below_depth and consolidate_sections."""
        # Create a more complex map structure for depth testing
        root = self.ctx.ditamap_root
        
        # Level 1 Content Module
        topic1_id = "topic_l1"
        topic1_fname = f"{topic1_id}.dita"
        topic1_ref = etree.SubElement(root, "topicref", href=f"topics/{topic1_fname}", **{"data-level": "1"})
        topic1 = _new_topic_with_title("Level 1 Content")
        self.ctx.topics[topic1_fname] = topic1
        
        # Level 1 Section
        section1 = etree.SubElement(root, "topicref", **{"data-level": "1"})
        section1_meta = etree.SubElement(section1, "topicmeta")
        section1_navtitle = etree.SubElement(section1_meta, "navtitle")
        section1_navtitle.text = "Level 1 Section"
        
        # Level 2 Content Module under Section 1
        topic2_id = "topic_l2"
        topic2_fname = f"{topic2_id}.dita"
        topic2_ref = etree.SubElement(section1, "topicref", href=f"topics/{topic2_fname}", **{"data-level": "2"})
        topic2 = _new_topic_with_title("Level 2 Content")
        body2 = etree.SubElement(topic2, "conbody")
        content2_para = etree.SubElement(body2, "p")
        content2_para.text = "This is level 2 content"
        self.ctx.topics[topic2_fname] = topic2
        
        # Level 2 Section under Section 1
        section2 = etree.SubElement(section1, "topicref", **{"data-level": "2"})
        section2_meta = etree.SubElement(section2, "topicmeta")
        section2_navtitle = etree.SubElement(section2_meta, "navtitle")
        section2_navtitle.text = "Level 2 Section"
        
        # Level 3 Content Module under Section 2
        topic3_id = "topic_l3"
        topic3_fname = f"{topic3_id}.dita"
        topic3_ref = etree.SubElement(section2, "topicref", href=f"topics/{topic3_fname}", **{"data-level": "3"})
        topic3 = _new_topic_with_title("Level 3 Content")
        body3 = etree.SubElement(topic3, "conbody")
        content3_para = etree.SubElement(body3, "p")
        content3_para.text = "This is level 3 content"
        self.ctx.topics[topic3_fname] = topic3
        
        # Make a copy of the original structure for comparison
        orig_map_str = etree.tostring(root)
        orig_topics = deepcopy(self.ctx.topics)
        
        # First, merge topics below depth 2
        merge_topics_below_depth(self.ctx, 2)
        
        # Then consolidate sections
        consolidate_sections(self.ctx)
        
        # Verify level 3 content was merged up to level 2
        self.assertEqual(len(section2.xpath(".//topicref[@href]")), 0)
        self.assertIn("href", section2.attrib)
        
        # Verify content from level 3 is preserved in level 2
        new_fname = section2.get("href").split("/")[-1]
        merged_topic = self.ctx.topics[new_fname]
        self.assertEqual(merged_topic.find("title").text, "Level 2 Section")
        
        # Check if the content includes the level 3 content
        paragraphs = merged_topic.findall(".//conbody/p")
        self.assertGreaterEqual(len(paragraphs), 1)
        found_l3_content = False
        for p in paragraphs:
            if p.text and "This is level 3 content" in p.text:
                found_l3_content = True
                break
        self.assertTrue(found_l3_content, "Level 3 content was not preserved in the merged topic")
        
        # Verify level 2 content module under section1 is still there (not merged)
        self.assertTrue(any(child.get("href") for child in section1 if child.tag == "topicref"))
        
        # Verify the total number of topics is correct
        # Original: 3 topics - topic_l3 (merged) = 2 topics + new merged topic = 3 total
        self.assertEqual(len(self.ctx.topics), 3)


if __name__ == '__main__':
    unittest.main()
