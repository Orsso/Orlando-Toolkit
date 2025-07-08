#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for the StructureTab cut/paste functionality.

These tests focus on the core logic of the cut/paste functionality,
using mock objects to simulate the tkinter UI where necessary.
"""

import sys
import unittest
from unittest import mock
import tkinter as tk
from tkinter import ttk
from lxml import etree as ET

# Add the project root to path for imports
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from orlando_toolkit.ui.structure_tab import StructureTab


class TestStructureTabCutPaste(unittest.TestCase):
    """Test case for testing the cut/paste functionality in StructureTab."""

    def setUp(self):
        """Set up the test environment."""
        # Create a root window that will be the parent of our StructureTab
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the window
        
        # Create a mock DitaContext to pass to StructureTab
        self.mock_context = mock.MagicMock()
        self.mock_context.metadata = {}
        
        # Create a sample XML structure for testing
        self.create_sample_structure()
        
        # Create the StructureTab instance
        self.tab = StructureTab(self.root)
        
        # Replace the tab's tree with a mock to avoid UI interactions
        self.tab.tree = mock.MagicMock()
        
        # Initialize the tab with our mock context
        self.tab.load_context(self.mock_context)
        
        # Set up the _item_map with mock treeview items and XML elements
        self.setup_item_map()
    
    def tearDown(self):
        """Clean up after the test."""
        # Destroy the root window
        self.root.destroy()
    
    def create_sample_structure(self):
        """Create a sample XML structure for testing."""
        # Create a sample DITA map XML structure
        xml_str = """
        <map>
            <topicref id="topic1" href="topic1.dita">
                <topicref id="topic2" href="topic2.dita">
                    <topicref id="topic3" href="topic3.dita" />
                </topicref>
                <topicref id="topic4" href="topic4.dita" />
            </topicref>
            <topicref id="topic5" href="topic5.dita" />
        </map>
        """
        self.xml_root = ET.fromstring(xml_str)
        self.topics = {}
        
        # Store references to topics by ID for easy access in tests
        for topic in self.xml_root.xpath('//topicref'):
            self.topics[topic.get('id')] = topic
    
    def setup_item_map(self):
        """Set up the _item_map with mock treeview items and XML elements."""
        # Create a mapping from tree item IDs to XML elements
        self.tab._item_map = {
            'item1': self.topics['topic1'],
            'item2': self.topics['topic2'],
            'item3': self.topics['topic3'],
            'item4': self.topics['topic4'],
            'item5': self.topics['topic5'],
        }
        
        # Store the reverse mapping for convenience in tests
        self.item_by_topic = {
            'topic1': 'item1',
            'topic2': 'item2',
            'topic3': 'item3',
            'topic4': 'item4',
            'topic5': 'item5',
        }
    
    def test_cut_selected(self):
        """Test the _cut_selected method."""
        # Set up tree selection mock to return a single selected item
        self.tab.tree.selection.return_value = ['item2']
        
        # Mock the push_undo_snapshot method
        self.tab._push_undo_snapshot = mock.MagicMock()
        self.tab._edit_journal = []
        self.tab._clipboard = None
        
        # Call the cut_selected method
        result = self.tab._cut_selected()
        
        # Check the result
        self.assertTrue(result, "Cut operation should return True on success")
        self.assertEqual(self.tab._clipboard, self.topics['topic2'], 
                         "Clipboard should contain the cut topic")
        
        # Check if undo snapshot was pushed
        self.tab._push_undo_snapshot.assert_called_once()
        
        # Check if edit journal entry was created
        self.assertEqual(len(self.tab._edit_journal), 1,
                         "An edit journal entry should be created")
        self.assertEqual(self.tab._edit_journal[0]['op'], 'cut',
                         "Edit journal entry should have 'cut' operation")
        
        # Check if the tree item was tagged as cut
        self.tab.tree.item.assert_called_with('item2', tags=('cut',))
    
    def test_cut_selected_no_selection(self):
        """Test cutting with no selection."""
        # Set up tree selection mock to return empty list
        self.tab.tree.selection.return_value = []
        
        # Mock the _show_status_message method
        self.tab._show_status_message = mock.MagicMock()
        
        # Call the cut_selected method
        result = self.tab._cut_selected()
        
        # Check the result
        self.assertFalse(result, "Cut operation should return False when no item is selected")
        
        # Check if status message was shown
        self.tab._show_status_message.assert_called_with("Please select a single topic to cut.")
    
    def test_clear_clipboard(self):
        """Test the _clear_clipboard method."""
        # Set up the clipboard with a cut item
        self.tab._clipboard = self.topics['topic2']
        self.tab._paste_mode = True
        
        # Set up the tree.get_children method to return all items
        self.tab.tree.get_children.return_value = ['item1', 'item2', 'item3', 'item4', 'item5']
        
        # Set up the tree.item method to return tags
        self.tab.tree.item.side_effect = lambda item_id, tag=None: {'tags': ('cut',)} if item_id == 'item2' and tag == 'tags' else {'tags': ()}
        
        # Call the clear_clipboard method
        self.tab._clear_clipboard()
        
        # Check if clipboard was cleared
        self.assertIsNone(self.tab._clipboard, "Clipboard should be cleared")
        self.assertFalse(self.tab._paste_mode, "Paste mode should be turned off")
    
    def test_paste_here(self):
        """Test the _paste_here method."""
        # Set up clipboard with a cut topic
        self.tab._clipboard = self.topics['topic2']
        self.tab._paste_mode = True
        
        # Set up mock for push_undo_snapshot
        self.tab._push_undo_snapshot = mock.MagicMock()
        self.tab._edit_journal = []
        
        # Mock tree.item to return text for items
        self.tab.tree.item.side_effect = lambda item_id, option=None: {'text': f"Topic {item_id[-1]}"} if option == 'text' else None
        
        # Call paste_here method to paste topic2 as child of topic5
        result = self.tab._paste_here('item5', mode='child')
        
        # Check result
        self.assertTrue(result, "Paste operation should return True on success")
        
        # Check if edit journal entry was created
        self.assertEqual(len(self.tab._edit_journal), 1,
                         "An edit journal entry should be created")
        self.assertEqual(self.tab._edit_journal[0]['op'], 'paste',
                         "Edit journal entry should have 'paste' operation")
        
        # Check clipboard state
        self.assertIsNone(self.tab._clipboard, "Clipboard should be cleared after paste")
        
        # Verify the XML structure was updated correctly
        # topic2 should now be a child of topic5
        self.assertIn(self.topics['topic2'], self.topics['topic5'],
                     "Cut topic should be a child of the target topic after paste")
    
    def test_paste_invalid_target(self):
        """Test pasting to an invalid target (paste onto itself or descendant)."""
        # Set up clipboard with a cut topic
        self.tab._clipboard = self.topics['topic1']  # topic1 has descendants
        self.tab._paste_mode = True
        
        # Mock _show_status_message
        self.tab._show_status_message = mock.MagicMock()
        
        # Try to paste topic1 as child of topic2 (which is a descendant of topic1)
        result = self.tab._paste_here('item2', mode='child')
        
        # Check result
        self.assertFalse(result, "Paste operation should return False with invalid target")
        
        # Check if error message was shown
        self.tab._show_status_message.assert_called_with(
            "Cannot paste a topic into itself or its descendants.")


if __name__ == "__main__":
    unittest.main()
