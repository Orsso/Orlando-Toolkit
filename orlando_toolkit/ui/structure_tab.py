# -*- coding: utf-8 -*-
"""Topic-structure configuration tab.

Allows the user to choose the maximum heading level that starts a new topic
and preview the resulting topic hierarchy extracted from the current
``DitaContext``.
"""

from __future__ import annotations

from typing import Optional
import copy
import tkinter as tk
from tkinter import ttk
from lxml import etree as ET
from orlando_toolkit.ui.dialogs import CenteredDialog

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext

__all__ = ["StructureTab"]


class StructureTab(ttk.Frame):
    """A tab that lets the user configure topic depth and preview structure."""

    def __init__(self, parent, depth_change_callback=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        # Store reference to parent app so we can access the master context
        self._main_app = parent.master if hasattr(parent, 'master') else None
        self.context: Optional["DitaContext"] = None
        self._depth_var = tk.IntVar(value=3)
        self._merge_enabled_var = tk.BooleanVar(value=True)
        self._depth_change_callback = depth_change_callback

        # ------------------------------------------------------------------
        # Clipboard for cut/paste (single selection only)
        # ------------------------------------------------------------------
        self._clipboard: ET.Element | None = None
        self._paste_mode: bool = False

        # ------------------------------------------------------------------
        # Deprecated move toolbar – attributes kept as None placeholders to
        # preserve references in legacy methods without functional impact.
        # ------------------------------------------------------------------
        self._btn_up = self._btn_down = self._btn_left = self._btn_right = None

        # --- UI ---------------------------------------------------------
        config_frame = ttk.LabelFrame(self, text="Topic splitting", padding=15)
        config_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(config_frame, text="Maximum heading level that starts a topic:").grid(row=0, column=0, sticky="w")
        depth_spin = ttk.Spinbox(
            config_frame,
            from_=1,
            to=9,
            textvariable=self._depth_var,
            width=3,
            command=self._on_depth_spin,
        )
        depth_spin.grid(row=0, column=1, sticky="w", padx=(5, 0))

        # Progress bar (hidden by default)
        self._progress = ttk.Progressbar(config_frame, mode="indeterminate")
        self._progress.grid(row=2, column=0, columnspan=3, sticky="we", pady=(4, 0))
        self._progress.grid_remove()

        # --- Toolbar for structural editing --------------------------------
        # (Removed - replaced with cut/paste functionality via context menu)

        # --- Search bar --------------------------------------------------
        search_frame = ttk.Frame(config_frame)
        search_frame.grid(row=0, column=3, padx=(20, 0))
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=18)
        search_entry.pack(side="left")
        search_entry.bind("<KeyRelease>", self._on_search_change)
        ttk.Button(search_frame, text="⟲", width=2, command=lambda: self._search_nav(-1)).pack(side="left", padx=1)
        ttk.Button(search_frame, text="⟳", width=2, command=lambda: self._search_nav(1)).pack(side="left", padx=1)

        # --- Heading filter ---------------------------------------------
        ttk.Button(config_frame, text="Heading filter…", command=self._open_heading_filter).grid(row=0, column=4, padx=(20, 0))

        # Internal search state
        self._search_matches: list[str] = []  # tree item IDs
        self._search_index: int = -1

        # Excluded styles state
        self._excluded_styles: dict[int, set[str]] = {}

        # Remember geometry of auxiliary dialogs for consistent placement
        self._filter_geom: str | None = None
        self._occ_geom: str | None = None

        # --- Preview ----------------------------------------------------
        preview_frame = ttk.LabelFrame(self, text="Topic preview", padding=10)
        preview_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(preview_frame, show="tree", selectmode="extended")
        self.tree.pack(side="left", expand=True, fill="both")

        # Prevent collapsing: re-open any item that tries to close
        self.tree.bind("<<TreeviewClose>>", self._on_close_attempt)
        self.tree.bind("<Double-1>", self._on_item_preview)
        self.tree.bind("<Button-3>", self._on_right_click)  # Right-click context menu

        # Visual styles for nodes
        self.tree.tag_configure("cut", foreground="gray")
        self.tree.tag_configure("paste_target", background="#e6f2ff")  # Light blue highlight for paste targets

        # Global shortcuts for undo/redo
        self.bind_all("<Control-z>", self._undo)
        self.bind_all("<Control-y>", self._redo)

        # Undo/redo stacks
        self._undo_stack: list = []
        self._redo_stack: list = []

        # Journal of structural edits so they can be replayed after depth rebuild
        self._edit_journal: list[dict] = []

        yscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        yscroll.pack(side="right", fill="y")

        # Enable horiz. scrolling with Shift+MouseWheel without a visible scrollbar
        self.tree.configure(yscrollcommand=yscroll.set)

        # --- Keyboard shortcuts and hover effects ------------------------
        self.tree.bind("<Control-x>", lambda e: self._cut_selected())
        self.tree.bind("<Control-v>", lambda e: self._handle_paste_shortcut(e))
        
        # Paste target hover effect when an item is cut
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

        def _on_shift_wheel(event):
            self.tree.xview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        self.tree.bind("<Shift-MouseWheel>", _on_shift_wheel)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_context(self, context: "DitaContext") -> None:
        # Keep reference to the *original* context so we can propagate changes
        self._main_context = context  # Original object owned by main app

        # Deep-copies for safe preview/undo operations
        self._orig_context = copy.deepcopy(context)
        self.context = copy.deepcopy(context)
        self._depth_var.set(int(context.metadata.get("topic_depth", 3)))
        self._merge_enabled_var.set(True)

        # Restore previously excluded style map if present
        self._excluded_styles = {int(k): set(v) for k, v in context.metadata.get("exclude_style_map", {}).items()}

        # Force realtime_merge flag
        context.metadata["realtime_merge"] = True

        self._rebuild_preview()
        self._update_toolbar_state()

        # Reset history and journal when new context loaded
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._edit_journal.clear()

        # Ensure original context retains realtime flag
        self._orig_context.metadata.setdefault("realtime_merge", True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rebuild_preview(self):
        self.tree.delete(*self.tree.get_children())
        if self.context is None or self.context.ditamap_root is None:
            return

        max_depth = int(self._depth_var.get())

        # Reset caches ---------------------------------------------------
        self._item_map = {}

        # Build heading cache from the *original* context so excluded styles remain visible
        self._heading_cache = {}
        source_root = getattr(self, "_orig_context", self.context).ditamap_root if hasattr(self, "_orig_context") else None
        if source_root is not None:
            for tref in source_root.xpath(".//topicref|.//topichead"):
                lvl = int(tref.get("data-level", 1))
                style_name = tref.get("data-style", f"Heading {lvl}")
                nav = tref.find("topicmeta/navtitle")
                title = nav.text.strip() if nav is not None and nav.text else "(untitled)"
                self._heading_cache.setdefault(lvl, {}).setdefault(style_name, []).append(title)
        else:
            self._heading_cache = {}

        def _clean(txt: str) -> str:
            return " ".join(txt.split())

        def _add_topicref(node: ET.Element, level: int, parent_id=""):
            for tref in [el for el in list(node) if el.tag in ("topicref", "topichead")]:
                t_level = int(tref.get("data-level", level))
                if t_level > max_depth:
                    continue
                navtitle_el = tref.find("topicmeta/navtitle")
                raw_title = navtitle_el.text if navtitle_el is not None else "(untitled)"
                title = _clean(raw_title)
                item_id = self.tree.insert(parent_id, "end", text=title)
                self._item_map[item_id] = tref
                _add_topicref(tref, t_level + 1, item_id)

        _add_topicref(self.context.ditamap_root, 1)

        # Expand everything so the hierarchy is fully visible
        for itm in self.tree.get_children(""):
            self.tree.item(itm, open=True)
            self._expand_all(itm)

        self._update_toolbar_state()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_depth_spin(self):
        # Live preview of depth change (local, does not trigger re-parse)
        new_depth = int(self._depth_var.get())
        if self.context:
            self.context.metadata["topic_depth"] = new_depth

            # Keep pristine copy & main context in sync so exporter sees update
            if hasattr(self, "_orig_context") and self._orig_context:
                self._orig_context.metadata["topic_depth"] = new_depth
            if hasattr(self, "_main_context") and self._main_context:
                self._main_context.metadata["topic_depth"] = new_depth
            self._maybe_merge_and_refresh()

    def _on_merge_toggle(self):
        if self.context is None:
            return
        new_val = bool(self._merge_enabled_var.get())
        self.context.metadata["realtime_merge"] = new_val

        if hasattr(self, "_orig_context") and self._orig_context:
            self._orig_context.metadata["realtime_merge"] = new_val
        if hasattr(self, "_main_context") and self._main_context:
            self._main_context.metadata["realtime_merge"] = new_val
        # Recompute preview to reflect potential content change
        self._maybe_merge_and_refresh()

    def _maybe_merge_and_refresh(self):
        if self.context is None:
            return

        # Always start from pristine copy to allow depth increases
        if hasattr(self, "_orig_context"):
            self.context = copy.deepcopy(self._orig_context)

        depth_limit = int(self._depth_var.get())
        realtime = True
        self.context.metadata["realtime_merge"] = realtime

        # Persist heading exclusions
        if self._excluded_styles:
            self.context.metadata["exclude_style_map"] = {str(k): list(v) for k, v in self._excluded_styles.items()}
        else:
            self.context.metadata.pop("exclude_style_map", None)

        if realtime:
            self._progress.grid()
            self._progress.start()
            self.update_idletasks()

            from orlando_toolkit.core.merge import merge_topics_below_depth, merge_topics_by_styles, consolidate_sections
            
            # Track whether any merge operation was performed
            merge_occurred = False
            
            # First apply depth filtering if needed
            if self.context.metadata.get("merged_depth") != depth_limit:
                merge_topics_below_depth(self.context, depth_limit)
                merge_occurred = True

            # Then apply heading exclusions if needed
            if self._excluded_styles and not self.context.metadata.get("merged_exclude_styles"):
                merge_topics_by_styles(self.context, self._excluded_styles)
                merge_occurred = True
            
            # Always apply section consolidation after any merge operation
            # Reset the consolidation flag if we did any merges to ensure it runs
            if merge_occurred:
                self.context.metadata.pop("consolidated_sections", None)
                
            # Apply consolidation as final step regardless of what other operations were performed
            consolidate_sections(self.context)

            self._progress.stop()
            self._progress.grid_remove()

        # Replay structural edits on refreshed context
        self._replay_edits()

        self._rebuild_preview()
        
    def _replay_edits(self):
        """Replay structural edits from the journal after rebuilding structure.
        This ensures that cut/paste operations are preserved even after depth changes.
        """
        if not hasattr(self, "_edit_journal") or not self._edit_journal:
            return
            
        # Create a map of hrefs to topic elements for efficient lookup
        href_map = {}
        
        # Helper function to build the href map recursively
        def build_href_map(elem):
            href = elem.get("href", "")
            if href:
                href_map[href] = elem
            for child in elem:
                build_href_map(child)
        
        # Build the map starting from the root
        if self.context and hasattr(self.context, "map_xml"):
            for child in self.context.map_xml:
                build_href_map(child)
        
        # Replay each edit operation
        for edit in self._edit_journal:
            op_type = edit.get("op")
            
            if op_type == "paste":
                # Get source and target elements by href
                source_href = edit.get("href", "")
                target_href = edit.get("target", "")
                mode = edit.get("mode", "after")
                
                source_elem = href_map.get(source_href)
                target_elem = href_map.get(target_href)
                
                # Skip if we can't find both elements
                if not source_elem or not target_elem:
                    continue
                
                # Remove source from its current location if it has a parent
                parent = source_elem.getparent()
                if parent is not None:
                    parent.remove(source_elem)
                
                # Place according to mode
                if mode == "after":
                    # Check if target is a section (has children or is a topichead)
                    has_children = len(target_elem) > 0
                    is_section = target_elem.tag == "topichead" or has_children
                    
                    if is_section:
                        # Place at top of section
                        if len(target_elem) > 0:
                            target_elem.insert(0, source_elem)
                        else:
                            target_elem.append(source_elem)
                    else:
                        # Place after as sibling
                        target_parent = target_elem.getparent()
                        if target_parent is not None:
                            index = target_parent.index(target_elem)
                            target_parent.insert(index + 1, source_elem)
                        else:
                            # If no parent, append to root
                            self.context.map_xml.append(source_elem)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _expand_all(self, item):
        for child in self.tree.get_children(item):
            self.tree.item(child, open=True)
            self._expand_all(child)

    def _on_close_attempt(self, event):
        item = self.tree.focus()
        if item:
            self.tree.item(item, open=True)
        return "break"

    def _on_item_preview(self, event):
        item = self.tree.focus()
        if not item or item not in self._item_map:
            return

        tref_el = self._item_map[item]

        # --- Build preview window -----------------------------------
        from tkinter import scrolledtext as _stxt
        import tempfile, webbrowser, pathlib

        preview_win = CenteredDialog(self, "XML Preview", (700, 500), "xml_preview")
        preview_win.title("XML Preview")
        preview_win.geometry("700x500")

        # Toolbar with "Open in browser" button
        toolbar = ttk.Frame(preview_win)
        toolbar.pack(fill="x")

        def _open_browser():
            """Render HTML preview to a temporary file and open it externally."""
            from orlando_toolkit.core.preview.xml_compiler import render_html_preview  # type: ignore

            html = render_html_preview(self.context, tref_el) if self.context else "<p>No preview</p>"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.html', prefix='orlando_preview_', mode='w', encoding='utf-8')
            tmp.write(html)
            tmp.flush()
            webbrowser.open_new_tab(pathlib.Path(tmp.name).as_uri())

        ttk.Button(toolbar, text="Open HTML in Browser", command=_open_browser).pack(side="left", padx=5, pady=2)

        # Raw XML display
        raw_txt = _stxt.ScrolledText(preview_win, wrap="none")
        raw_txt.pack(fill="both", expand=True)

        from orlando_toolkit.core.preview.xml_compiler import get_raw_topic_xml  # type: ignore
        xml_str = get_raw_topic_xml(self.context, tref_el) if self.context else ""
        raw_txt.insert("1.0", xml_str)
        raw_txt.yview_moveto(0)

    def _update_toolbar_state(self, event=None):  # noqa: D401
        """Deprecated toolbar state handler - now a no-op."""
        return

    def _on_right_click(self, event):
        """Handle right-click context menu on tree items."""
        import tkinter as tk
        
        # Identify clicked item
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Select the clicked item if not already selected
        current_selection = list(self.tree.selection())
        if item not in current_selection:
            self.tree.selection_set([item])
        
        selected_items = list(self.tree.selection())
        if not selected_items:
            return
        
        # Create context menu
        context_menu = tk.Menu(self, tearoff=0)
        
        # Rename option (only for single selection)
        if len(selected_items) == 1:
            context_menu.add_command(label="Rename", command=lambda: self._show_status_message("Rename functionality will be implemented in a future update."))
            context_menu.add_separator()
        
        # Cut/Paste options for single selection
        context_menu.add_command(label="Cut", command=self._cut_selected)
        if self._clipboard is not None:
            # Show paste option only if clipboard has content
            paste_menu = tk.Menu(context_menu, tearoff=0)
            context_menu.add_cascade(label="Paste", menu=paste_menu)
            paste_menu.add_command(label="After", command=lambda: self._paste_here(item, "after"))
            
        context_menu.add_separator()
        
        # Delete option (always available)
        delete_text = "Delete Permanently" if len(selected_items) == 1 else f"Delete {len(selected_items)} Topics"
        context_menu.add_command(label=delete_text, command=lambda: self._show_status_message("Delete functionality will be implemented in a future update."))
        
        # Show context menu
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _cut_selected(self):
        """Cut the selected topic."""
        selected_items = list(self.tree.selection())
        if len(selected_items) != 1:
            self._show_status_message("Please select a single topic to cut.")
            return False
        
        self._push_undo_snapshot()
        item = selected_items[0]
        self._clipboard = self._item_map.get(item)
        if self._clipboard is None:
            self._show_status_message("Error: Unable to find the selected topic.")
            return False
            
        self._paste_mode = True
        self._edit_journal.append({"op": "cut", "href": self._clipboard.get("href", "")})
        
        # Visual indication for cut items
        self.tree.item(item, tags=("cut",))
        self._show_status_message("Topic cut. Use Paste to place it in a new location.")
        return True

    def _clear_clipboard(self):
        """Clear the clipboard state and visual indicators."""
        if self._clipboard is None:
            return
            
        # Remove visual indication from all items without risking deep recursion
        visited = set()
        stack = list(self.tree.get_children(""))
        while stack:
            item = stack.pop()
            if item in visited:
                continue
            visited.add(item)
            current_tags = list(self.tree.item(item, "tags"))
            if "cut" in current_tags or "paste_target" in current_tags:
                new_tags = [tag for tag in current_tags if tag not in ("cut", "paste_target")]
                self.tree.item(item, tags=new_tags if new_tags else ())
            # Push children onto stack
            stack.extend(self.tree.get_children(item))
                
        self._clipboard = None
        self._paste_mode = False

    def _paste_here(self, target_item, mode="after"):
        """Paste previously cut node to the specified target.
        
        Args:
            target_item: The tree item to paste at
            mode: The paste mode ('after' = as sibling after target)
                  When target is a section, 'after' will place at top of section.
        
        Returns:
            bool: True if paste was successful, False otherwise
        """
        if self._clipboard is None or not self._paste_mode:
            self._show_status_message("Nothing to paste. Cut a topic first.")
            return False
        
        # Get XML references
        cut_tref = self._clipboard
        target_tref = self._item_map.get(target_item)
        
        if target_tref is None:
            self._show_status_message("Invalid paste target.")
            return False
        
        # Validate: can't paste into itself or its descendants
        if cut_tref is target_tref or target_tref in cut_tref.xpath('.//topicref|.//topichead'):
            self._show_status_message("Cannot paste a topic into itself or its descendants.")
            return False
        
        # Create undo snapshot before modifying structure
        self._push_undo_snapshot()
        
        # Remove cut node from its current location
        parent = cut_tref.getparent()
        if parent is not None:
            parent.remove(cut_tref)
        
        # Paste at target location
        paste_description = ""  # Will describe where the topic ended up
        if mode == "child":
            # Always paste as the first child of the target element
            target_tref.insert(0, cut_tref)
            paste_description = "as first child"
        elif mode == "after":
            # Check if target is a section (has children)
            has_children = len(target_tref) > 0
            is_section = target_tref.tag == "topichead" or has_children
            
            if is_section:
                # Place at top of section (as first child)
                if len(target_tref) > 0:
                    # Insert as first child
                    target_tref.insert(0, cut_tref)
                else:
                    # No existing children, just append
                    target_tref.append(cut_tref)
                paste_description = "at the top of section"
            else:
                # Regular topic - insert after as sibling
                target_parent = target_tref.getparent()
                if target_parent is not None:
                    # Find the index of the target in its parent's children
                    index = target_parent.index(target_tref)
                    # Insert the cut topic right after the target
                    target_parent.insert(index + 1, cut_tref)
                else:
                    # If target has no parent (shouldn't happen), just append to root
                    self.context.map_xml.append(cut_tref)
                paste_description = "after the target"
        
        # Record operation in journal for history replay
        self._edit_journal.append({
            "op": "paste",
            "href": cut_tref.get("href", ""),
            "target": target_tref.get("href", ""),
            "mode": mode
        })
        
        # Rebuild the tree view to show the new structure
        self._rebuild_preview()
        
        # Clear the clipboard state
        self._clear_clipboard()
        
        # Fallback description if none was set (should not normally happen)
        if not paste_description:
            paste_description = "in the selected location"
        self._show_status_message(f"Topic pasted successfully {paste_description}.")
        return True

    def _handle_paste_shortcut(self, event=None):
        """Handle the Ctrl+V keyboard shortcut for pasting.
        
        Will paste after the currently selected item.
        If multiple items are selected, will paste after the first one.
        If no selection, shows a message.
        """
        if self._clipboard is None:
            self._show_status_message("Nothing to paste. Cut a topic first.")
            return
        
        selected_items = list(self.tree.selection())
        if not selected_items:
            self._show_status_message("Select a target topic to paste after first.")
            return
        
        # Use first selected item as target
        target_item = selected_items[0]
        self._paste_here(target_item, mode="after")

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    def _on_search_change(self, event=None):
        term = self._search_var.get().strip().lower()
        self._search_matches.clear()
        self._search_index = -1
        if not term:
            return

        for item_id, tref in self._item_map.items():
            title = self.tree.item(item_id, "text").lower()
            if term in title:
                self._search_matches.append(item_id)

        self._search_nav(1)

    def _search_nav(self, delta: int):
        if not self._search_matches:
            return
        self._search_index = (self._search_index + delta) % len(self._search_matches)
        target = self._search_matches[self._search_index]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
    
    # ------------------------------------------------------------------
    # Heading filter dialog
    # ------------------------------------------------------------------

    def _collect_headings(self):
        """Return cached heading dict built during preview rebuild."""
        return getattr(self, "_heading_cache", {})

    def _open_heading_filter(self):
        headings = self._collect_headings()
        if not headings:
            return

        dlg = CenteredDialog(self, "Heading filter", (483, 520), "heading_filter")

        # Paned window: left = style checklist; right = occurrences list
        paned = ttk.Panedwindow(dlg, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ---------------- Left: checklist -----------------
        left_frm = ttk.Frame(paned)
        paned.add(left_frm, weight=1)

        canvas = tk.Canvas(left_frm, highlightthickness=0)
        vscroll = ttk.Scrollbar(left_frm, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=frame, anchor="nw")

        def _on_frame_config(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        frame.bind("<Configure>", _on_frame_config)

        # ---------------- Right: occurrence list ----------------
        right_frm = ttk.Frame(paned)
        paned.add(right_frm, weight=1)

        occ_lbl = ttk.Label(right_frm, text="Occurrences", font=("Arial", 10, "bold"))
        occ_lbl.pack(anchor="w", padx=5, pady=(5, 2))

        occ_scroll = ttk.Scrollbar(right_frm, orient="vertical")
        occ_list = tk.Listbox(right_frm, yscrollcommand=occ_scroll.set, height=15)
        occ_scroll.config(command=occ_list.yview)
        occ_list.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        occ_scroll.pack(side="right", fill="y", pady=5)

        row_idx = 0
        vars_map = {}
        for lvl in sorted(headings.keys()):
            styles_dict = headings[lvl]
            # Label for level
            lvl_lbl = ttk.Label(frame, text=f"Level {lvl}", font=("Arial", 10, "bold"))
            lvl_lbl.grid(row=row_idx, column=0, sticky="w", padx=5, pady=(6, 2))
            row_idx += 1

            for style_name, titles in sorted(styles_dict.items()):
                row_frm = ttk.Frame(frame)
                row_frm.grid(row=row_idx, column=0, sticky="w", padx=15, pady=1)

                key = (lvl, style_name)
                var = tk.BooleanVar(value=(style_name not in getattr(self, "_excluded_styles", {}).get(lvl, set())))

                def _on_toggle(l=lvl, s=style_name, v=var):
                    # update exclusion map
                    if v.get():
                        if l in self._excluded_styles and s in self._excluded_styles[l]:
                            self._excluded_styles[l].discard(s)
                            if not self._excluded_styles[l]:
                                self._excluded_styles.pop(l)
                    else:
                        self._excluded_styles.setdefault(l, set()).add(s)

                    # Sync metadata in all contexts
                    for ctx in (self.context, getattr(self, "_orig_context", None), getattr(self, "_main_context", None)):
                        if ctx is None:
                            continue
                        if self._excluded_styles:
                            ctx.metadata["exclude_style_map"] = {str(k): list(v) for k, v in self._excluded_styles.items()}
                        else:
                            ctx.metadata.pop("exclude_style_map", None)
                        ctx.metadata.pop("merged_exclude_styles", None)

                    self._maybe_merge_and_refresh()

                titles_copy = list(titles)  # local copy for closure

                def _on_select(event, lst=titles_copy, sty=style_name):
                    # Ignore clicks that originate on the Checkbutton itself
                    if isinstance(event.widget, tk.Checkbutton):
                        return
                    occ_list.delete(0, "end")
                    occ_lbl.config(text=f"Occurrences – {sty}")
                    for t in lst:
                        occ_list.insert("end", t)

                chk = ttk.Checkbutton(row_frm, variable=var, command=_on_toggle, width=2)
                chk.pack(side="left", anchor="w")

                lbl = ttk.Label(row_frm, text=f"{style_name} ({len(titles)})")
                lbl.pack(side="left", anchor="w")

                lbl.bind("<Button-1>", _on_select)

                vars_map[key] = var
                row_idx += 1

        # Mouse wheel scrolling when pointer over left list
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Bind to canvas only, not globally, to avoid dangling callbacks after dialog closes
        canvas.bind("<MouseWheel>", _on_mousewheel)

    # ------------------------------------------------------------------
    # Context sync helper
    # ------------------------------------------------------------------

    def _context_modified_sync(self, key: str, value):
        for ctx in (getattr(self, "_orig_context", None), getattr(self, "_main_context", None)):
            if ctx:
                ctx.metadata[key] = value 

    # ------------------------------------------------------------------
    # Status message helper
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Paste hover visualization helpers
    # ------------------------------------------------------------------
    
    def _on_tree_motion(self, event):
        """Handle mouse motion over the tree to highlight valid paste targets.
        Only activates when an item is currently cut (clipboard has content).
        """
        if self._clipboard is None:
            return
            
        # Identify item under cursor
        item = self.tree.identify_row(event.y)
        if item == "":
            self._clear_paste_target_highlights()
            return
            
        # Verify it's a valid paste target
        target_tref = self._item_map.get(item)
        if target_tref is None:
            self._clear_paste_target_highlights()
            return
            
        # Check if it's a valid target (not the cut item or its descendant)
        cut_tref = self._clipboard
        
        # Check for valid paste target
        if (cut_tref is target_tref or 
            target_tref in cut_tref.xpath('.//topicref|.//topichead')):
            self._clear_paste_target_highlights()
            return
            
        # Apply highlight to target
        self._clear_paste_target_highlights()
        current_tags = list(self.tree.item(item, "tags"))
        if "paste_target" not in current_tags:
            current_tags.append("paste_target")
            self.tree.item(item, tags=tuple(current_tags))
    
    def _on_tree_leave(self, event):
        """Handle mouse leaving the tree area."""
        self._clear_paste_target_highlights()
    
    def _clear_paste_target_highlights(self):
        """Remove all paste target highlights from the tree."""
        def clear_tags_recursive(item):
            children = self.tree.get_children(item)
            for child in children:
                current_tags = list(self.tree.item(child, "tags"))
                if "paste_target" in current_tags:
                    new_tags = [tag for tag in current_tags if tag != "paste_target"]
                    self.tree.item(child, tags=tuple(new_tags) if new_tags else ())
                clear_tags_recursive(child)
        
        # Start with root items
        clear_tags_recursive("")
    
    # ------------------------------------------------------------------
    # Undo/redo functionality
    # ------------------------------------------------------------------
    
    def _push_undo_snapshot(self):
        """Take a snapshot of the current state for undo/redo."""
        if not hasattr(self, "context") or self.context is None:
            return
            
        # Make a deep copy of the current XML structure
        if hasattr(self.context, "map_xml") and self.context.map_xml is not None:
            snapshot = copy.deepcopy(self.context.map_xml)
            self._undo_stack.append(snapshot)
            self._redo_stack.clear()  # Clear redo stack when a new action is taken
    
    def _undo(self, event=None):
        """Restore previous state from the undo stack."""
        if not self._undo_stack:
            self._show_status_message("Nothing to undo.")
            return
            
        # Save current state to redo stack
        if hasattr(self.context, "map_xml") and self.context.map_xml is not None:
            current = copy.deepcopy(self.context.map_xml)
            self._redo_stack.append(current)
            
            # Restore previous state
            previous = self._undo_stack.pop()
            self.context.map_xml = previous
            self._rebuild_preview()
            self._show_status_message("Undo successful.")
    
    def _redo(self, event=None):
        """Restore next state from the redo stack."""
        if not self._redo_stack:
            self._show_status_message("Nothing to redo.")
            return
            
        # Save current state to undo stack
        if hasattr(self.context, "map_xml") and self.context.map_xml is not None:
            current = copy.deepcopy(self.context.map_xml)
            self._undo_stack.append(current)
            
            # Restore next state
            next_state = self._redo_stack.pop()
            self.context.map_xml = next_state
            self._rebuild_preview()
            self._show_status_message("Redo successful.")
    
    # ------------------------------------------------------------------
    # Status message helper
    # ------------------------------------------------------------------

    def _show_status_message(self, message, duration=3000):
        """Display a temporary status message to the user.
        
        Args:
            message (str): Message to display
            duration (int): Duration in milliseconds before auto-dismissing
        """
        if hasattr(self, "_status_message_id") and self._status_message_id:
            self.after_cancel(self._status_message_id)
            self._status_message_id = None
            
        # Create status bar if it doesn't exist
        if not hasattr(self, "_status_label") or not self._status_label:
            self._status_label = ttk.Label(self, text="", anchor="w", background="#f0f0f0", relief="sunken")
            self._status_label.pack(side="bottom", fill="x", padx=5, pady=(0, 5))
        
        # Show message
        self._status_label.config(text=message)
        self._status_label.update_idletasks()
        
        # Schedule auto-dismiss
        def _clear_status():
            if hasattr(self, "_status_label") and self._status_label:
                self._status_label.config(text="")
            self._status_message_id = None
            
        self._status_message_id = self.after(duration, _clear_status)