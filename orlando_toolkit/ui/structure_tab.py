# -*- coding: utf-8 -*-
"""Topic-structure configuration tab.

Allows the user to choose the maximum heading level that starts a new topic
and preview the resulting topic hierarchy extracted from the current
``DitaContext``.
"""

from __future__ import annotations

from typing import Optional
import copy
import logging
import tkinter as tk
from tkinter import ttk
from lxml import etree as ET
from orlando_toolkit.ui.dialogs import CenteredDialog

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext

log = logging.getLogger(__name__)

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
        toolbar = ttk.Frame(config_frame)
        toolbar.grid(row=0, column=2, padx=(15, 0))

        self._btn_up = ttk.Button(toolbar, text="↑", width=3, command=lambda: self._move("up"))
        self._btn_down = ttk.Button(toolbar, text="↓", width=3, command=lambda: self._move("down"))
        self._btn_left = ttk.Button(toolbar, text="◀", width=3, command=lambda: self._move("promote"))
        self._btn_right = ttk.Button(toolbar, text="▶", width=3, command=lambda: self._move("demote"))

        for i, b in enumerate((self._btn_up, self._btn_down, self._btn_left, self._btn_right)):
            b.grid(row=0, column=i, padx=1)
        # Hidden debug button – revealed via Ctrl+Shift+D
        self._btn_debug = ttk.Button(toolbar, text="🐞", width=2, command=self._start_debug_trace)
        self._btn_debug.grid(row=0, column=4, padx=(6, 0))
        self._btn_debug.grid_remove()
        # Key chord to reveal the button for power users
        self.bind_all("<Control-Shift-D>", lambda e: self._btn_debug.grid())

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
        self.tree.bind("<<TreeviewSelect>>", self._update_toolbar_state)
        self.tree.bind("<Double-1>", self._on_item_preview)
        self.tree.bind("<Button-3>", self._on_right_click)  # Right-click context menu

        # Global shortcuts for undo/redo
        self.bind_all("<Control-z>", self._undo)
        self.bind_all("<Control-y>", self._redo)



        # Undo/redo stacks
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

        # Journal of structural edits so they can be replayed after depth rebuild
        self._edit_journal: list[dict] = []

        yscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        yscroll.pack(side="right", fill="y")

        # Enable horiz. scrolling with Shift+MouseWheel without a visible scrollbar
        self.tree.configure(yscrollcommand=yscroll.set)

        # ------------------------------------------------------------------
        # Tooltip for showing style info on hover
        # ------------------------------------------------------------------
        from orlando_toolkit.ui.custom_widgets import ToolTip  # local import to avoid cycles
        self._tooltip = ToolTip(self)
        self.tree.bind("<Motion>", self._on_tree_hover)
        self.tree.bind("<Leave>", lambda e: self._tooltip.hide())

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

        log.debug("Loading context with %d topics", len(context.topics))
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
        log.debug("Rebuilding preview (depth=%s)", self._depth_var.get())
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
        log.debug("Depth spin changed to %s", self._depth_var.get())
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
        log.debug("Realtime merge toggled to %s", bool(self._merge_enabled_var.get()))
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
        log.debug("Merge/refresh triggered (depth=%s, excluded=%s)", self._depth_var.get(), bool(getattr(self, '_excluded_styles', {})))
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

            from orlando_toolkit.core.merge import merge_topics_below_depth

            if self.context.metadata.get("merged_depth") != depth_limit:
                merge_topics_below_depth(self.context, depth_limit)

            # Apply heading exclusions on the fly
            if self._excluded_styles and not self.context.metadata.get("merged_exclude_styles"):
                from orlando_toolkit.core.merge import merge_topics_by_styles
                merge_topics_by_styles(self.context, self._excluded_styles)

            self._progress.stop()
            self._progress.grid_remove()

        # Replay structural edits on refreshed context
        self._replay_edits()

        self._rebuild_preview()

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

    def _update_toolbar_state(self, event=None):
        """Enable/disable toolbar buttons based on current selection."""
        sel = self.tree.selection()
        enabled = len(sel) > 0
        for btn in (self._btn_up, self._btn_down, self._btn_left, self._btn_right):
            btn.config(state="normal" if enabled else "disabled")

    # ------------------------------------------------------------------
    # Tooltip handlers (moved to class level)
    # ------------------------------------------------------------------
    def _on_tree_hover(self, event):
        """Display tooltip with style name when mouse hovers over a Treeview item."""
        item_id = self.tree.identify_row(event.y)
        if not item_id or item_id not in getattr(self, "_item_map", {}):
            self._tooltip.hide()
            return
        tref = self._item_map[item_id]
        style_name = tref.get("data-style", "Unknown style")
        level = tref.get("data-level", "?")
        text = f"Style: {style_name}\nLevel: {level}"
        self._tooltip.show(text, event.x_root, event.y_root)

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
            context_menu.add_command(label="Rename", command=self._rename_selected)
            context_menu.add_separator()
        
        # Merge option (only if multiple selection and all in same section)
        if len(selected_items) > 1:
            if self._can_merge_selection(selected_items):
                context_menu.add_command(label="Merge Topics", command=self._merge_selected)
            context_menu.add_separator()
        
        # Delete option (always available)
        delete_text = "Delete Permanently" if len(selected_items) == 1 else f"Delete {len(selected_items)} Topics"
        context_menu.add_command(label=delete_text, command=self._delete_selected_with_confirmation)
        
        # Show context menu
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _can_merge_selection(self, selected_items):
        """Check if selected items can be merged (all in same section)."""
        if len(selected_items) < 2:
            return False
        
        # Get the parent (section) for each selected item
        parents = set()
        for item in selected_items:
            tref = self._item_map.get(item)
            if tref is None:
                return False
            parent = tref.getparent()
            if parent is None:
                return False
            parents.add(parent)
        
        # All items must have the same parent (same section)
        return len(parents) == 1

    def _rename_selected(self):
        """Rename the selected topic."""
        selected = list(self.tree.selection())
        if len(selected) != 1:
            return
        
        item = selected[0]
        tref = self._item_map.get(item)
        if not tref:
            return
        
        # Get current title
        current_title = self.tree.item(item, "text")
        
        # Create rename dialog
        from orlando_toolkit.ui.dialogs import CenteredDialog
        dlg = CenteredDialog(self, "Rename Topic", (400, 150), "rename_topic")
        
        ttk.Label(dlg, text="Topic title:").pack(anchor="w", padx=10, pady=(10, 5))
        
        title_var = tk.StringVar(value=current_title)
        title_entry = ttk.Entry(dlg, textvariable=title_var, width=50)
        title_entry.pack(padx=10, pady=5, fill="x")
        title_entry.select_range(0, tk.END)
        title_entry.focus()
        
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        
        def _do_rename():
            new_title = title_var.get().strip()
            if new_title and new_title != current_title:
                # Update the topic title in the XML
                href = tref.get("href")
                if href:
                    topic_filename = href.split("/")[-1]
                    topic_el = self.context.topics.get(topic_filename)
                    if topic_el is not None:
                        title_el = topic_el.find("title")
                        if title_el is not None:
                            title_el.text = new_title
                        
                        # Rebuild preview to show changes
                        self._rebuild_preview()
                        self._restore_selection([tref])
            dlg.destroy()
        
        def _do_cancel():
            dlg.destroy()
        
        ttk.Button(btn_frame, text="OK", command=_do_rename).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=_do_cancel).pack(side="right")
        
        # Bind Enter key to OK
        title_entry.bind("<Return>", lambda e: _do_rename())

    def _delete_selected_with_confirmation(self):
        """Delete selected topics with confirmation dialog."""
        selected = list(self.tree.selection())
        if not selected:
            return
        
        # Create confirmation dialog
        from orlando_toolkit.ui.dialogs import CenteredDialog
        dlg = CenteredDialog(self, "Delete Confirmation", (400, 200), "delete_confirm")
        
        if len(selected) == 1:
            message = f"Are you sure you want to permanently delete this topic?\n\nThis action cannot be undone."
        else:
            message = f"Are you sure you want to permanently delete {len(selected)} topics?\n\nThis action cannot be undone."
        
        ttk.Label(dlg, text=message, wraplength=350, justify="center").pack(padx=20, pady=20)
        
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        
        def _do_delete():
            dlg.destroy()
            self._delete_selected_permanently(selected)
        
        def _do_cancel():
            dlg.destroy()
        
        # Make delete button red/warning style
        delete_btn = ttk.Button(btn_frame, text="Delete Permanently", command=_do_delete)
        delete_btn.pack(side="right", padx=5)
        
        ttk.Button(btn_frame, text="Cancel", command=_do_cancel).pack(side="right")

    def _delete_selected_permanently(self, selected_items):
        log.debug("ui_delete_requested", extra={"event": "ui_delete_requested", "count": len(selected_items)})
        """Permanently delete the specified items."""
        if not selected_items:
            return
        
        # Snapshot for undo
        self._push_undo_snapshot()
        
        removed_trefs = []
        changed = False
        
        # Process in reverse order to avoid index shifting
        for item in reversed(selected_items):
            tref = self._item_map.get(item)
            if tref is None:
                continue
            parent = tref.getparent()
            if parent is None:
                continue
            
            # Remove from ditamap
            parent.remove(tref)
            removed_trefs.append(tref)
            changed = True
            
            # Remove from topics if it has an href
            href = tref.get("href")
            if href:
                topic_filename = href.split("/")[-1]
                self.context.topics.pop(topic_filename, None)
        
        if changed:
            # Keep pristine context in sync
            if hasattr(self, "_orig_context") and self._orig_context:
                import copy as _cpy
                self._orig_context.ditamap_root = _cpy.deepcopy(self.context.ditamap_root)
            
            self._rebuild_preview()
            
            # Record deletions in journal
            for tref in removed_trefs:
                href = tref.get("href", "")
                self._edit_journal.append({"op": "delete", "href": href})

    def _merge_selected(self):
        sel_items = list(self.tree.selection())
        log.debug("ui_merge_requested", extra={"event": "ui_merge_requested", "selection": sel_items})
        """Merge multiple selected topics into the first one."""
        selected = list(self.tree.selection())
        if len(selected) < 2:
            return
        
        # Verify all are in same section
        if not self._can_merge_selection(selected):
            return
        
        # Snapshot for undo
        self._push_undo_snapshot()
        
        # Get topic references in selection order
        selected_trefs = []
        for item in selected:
            tref = self._item_map.get(item)
            if tref is not None:
                selected_trefs.append(tref)
        
        if len(selected_trefs) < 2:
            return
        
        # First topic becomes the target
        target_tref = selected_trefs[0]
        target_href = target_tref.get("href")
        if not target_href:
            return
        
        target_filename = target_href.split("/")[-1]
        target_topic = self.context.topics.get(target_filename)
        if target_topic is None:
            return
        
        # Merge each subsequent topic into the target
        removed_trefs = []
        for source_tref in selected_trefs[1:]:
            source_href = source_tref.get("href")
            if not source_href:
                continue
            
            source_filename = source_href.split("/")[-1]
            source_topic = self.context.topics.get(source_filename)
            if source_topic is None:
                continue
            
            # Copy content with title preservation (Option B format)
            self._copy_content_with_title(source_topic, target_topic)
            
            # Remove source topic from ditamap
            parent = source_tref.getparent()
            if parent is not None:
                parent.remove(source_tref)
                removed_trefs.append(source_tref)
            
            # Remove source topic from context
            self.context.topics.pop(source_filename, None)
        
        if removed_trefs:
            # Keep pristine context in sync
            if hasattr(self, "_orig_context") and self._orig_context:
                import copy as _cpy
                self._orig_context.ditamap_root = _cpy.deepcopy(self.context.ditamap_root)
            
            self._rebuild_preview()
            self._restore_selection([target_tref])
            
            # Record merges in journal
            for tref in removed_trefs:
                href = tref.get("href", "")
                self._edit_journal.append({"op": "merge", "href": href, "target": target_href})
                # Structured event
                log.debug("ui_merge", extra={"event": "ui_merge", "src": href, "tgt": target_href})

    def _copy_content_with_title(self, source_topic, target_topic):
        """Copy content from source to target topic, preserving source title as emphasized text."""
        from orlando_toolkit.core.utils import generate_dita_id
        
        # Get target body
        target_body = target_topic.find("conbody")
        if target_body is None:
            target_body = ET.SubElement(target_topic, "conbody")
        
        # Get source title and body
        source_title_el = source_topic.find("title")
        source_body = source_topic.find("conbody")
        
        # Add source title as emphasized text (Option B format)
        if source_title_el is not None and source_title_el.text:
            title_p = ET.Element("p", id=generate_dita_id())
            title_b = ET.SubElement(title_p, "b")
            title_b.text = source_title_el.text.strip()
            target_body.append(title_p)
        
        # Copy all content from source body
        if source_body is not None:
            from orlando_toolkit.core.merge import BLOCK_LEVEL_TAGS
            from copy import deepcopy
            
            for child in list(source_body):
                if child.tag in BLOCK_LEVEL_TAGS:
                    # Deep copy and ensure unique IDs
                    new_child = deepcopy(child)
                    
                    # Regenerate IDs to avoid duplicates
                    if "id" in new_child.attrib:
                        new_child.set("id", generate_dita_id())
                    
                    for el in new_child.xpath('.//*[@id]'):
                        el.set("id", generate_dita_id())
                    
                    target_body.append(new_child)

    # ------------------------------------------------------------------
    # Structural mutations
    # ------------------------------------------------------------------

    def _move(self, direction: str):
        sel = list(self.tree.selection())
        log.debug("ui_move_requested", extra={"event": "ui_move_requested", "direction": direction, "selection": sel})
        def _shift_levels(tref_el: ET.Element, delta: int):
            """Recursively adjust data-level on *tref_el* and its descendants."""
            new_lvl = max(1, int(tref_el.get("data-level", 1)) + delta)
            tref_el.set("data-level", str(new_lvl))
            for child in tref_el.xpath('.//topicref|.//topichead'):
                _shift_levels(child, delta)

        selected = list(self.tree.selection())
        if not selected:
            return

        # Snapshot for undo
        self._push_undo_snapshot()

        changed = False
        selected_trefs: list[ET.Element] = []

        # Build groups of contiguous selections per parent
        by_parent: dict[ET.Element, list[tuple[int, ET.Element]]] = {}
        for sel in selected:
            tref = self._item_map.get(sel)
            if tref is None or tref.getparent() is None:
                continue
            parent = tref.getparent()
            idx = list(parent).index(tref)
            by_parent.setdefault(parent, []).append((idx, tref))

        # Process each parent group separately
        for parent, items in by_parent.items():
            # Sort by index (visual order within parent)
            items.sort(key=lambda t: t[0])

            if direction in ("up", "promote"):
                forward_iter = items
            else:  # down/demote process from bottom to top
                forward_iter = list(reversed(items))

            if direction in ("up", "down"):
                for idx, tref in forward_iter:
                    sibs = list(parent)
                    cur_idx = sibs.index(tref)
                    if direction == "up" and cur_idx > 0:
                        parent.remove(tref)
                        parent.insert(cur_idx - 1, tref)
                        changed = True
                        selected_trefs.append(tref)
                    elif direction == "down" and cur_idx < len(sibs) - 1:
                        parent.remove(tref)
                        parent.insert(cur_idx + 1, tref)
                        changed = True
                        selected_trefs.append(tref)
            elif direction == "promote":
                grand = parent.getparent()
                if grand is None:
                    continue
                insert_pos = list(grand).index(parent) + 1
                for _, tref in forward_iter:
                    parent.remove(tref)
                    grand.insert(insert_pos, tref)
                    insert_pos += 1
                    changed = True
                    selected_trefs.append(tref)
                    _shift_levels(tref, -1)
            elif direction == "demote":
                # Use the left sibling of the *first* item as new parent
                first_idx, tref_sample = items[0]
                # Abort when no left sibling exists (cannot demote)
                if first_idx == 0:
                    continue

                # Abort if new level would exceed current depth preview
                cur_level = int(tref_sample.get("data-level", 1))
                max_depth = int(self._depth_var.get())
                if cur_level + 1 > max_depth:
                    continue

                anchor = list(parent)[first_idx - 1]
                for _, tref in items:  # append in original visual order
                    parent.remove(tref)
                    anchor.append(tref)
                    changed = True
                    selected_trefs.append(tref)
                    _shift_levels(tref, +1)

        if changed:
            # Keep pristine context in sync so heading cache rebuild sees nodes
            if hasattr(self, "_orig_context") and self._orig_context:
                import copy as _cpy
                self._orig_context.ditamap_root = _cpy.deepcopy(self.context.ditamap_root)

            self._rebuild_preview()
            self._restore_selection(selected_trefs)

            # Record move in journal
            for tref in selected_trefs:
                href = tref.get("href", "")
                self._edit_journal.append({"op": "move", "href": href, "dir": direction})
            log.debug("ui_move", extra={"event": "ui_move", "href": href, "dir": direction})



    # ------------------------------------------------------------------
    # Undo / Redo helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> bytes:
        """Serialize current ditamap for undo/redo."""
        if self.context and self.context.ditamap_root is not None:
            from lxml import etree as _ET
            return _ET.tostring(self.context.ditamap_root)
        return b""

    def _push_undo_snapshot(self):
        snap = self._snapshot()
        if snap:
            self._undo_stack.append(snap)
            self._redo_stack.clear()

    def _undo(self, event=None):
        if not self._undo_stack:
            return "break"
        snap = self._undo_stack.pop()
        if snap:
            # Push current to redo
            current = self._snapshot()
            if current:
                self._redo_stack.append(current)
            self._restore_snapshot(snap)
        return "break"

    def _redo(self, event=None):
        if not self._redo_stack:
            return "break"
        snap = self._redo_stack.pop()
        if snap:
            current = self._snapshot()
            if current:
                self._undo_stack.append(current)
            self._restore_snapshot(snap)
        return "break"

    def _restore_snapshot(self, snap: bytes):
        from lxml import etree as _ET
        try:
            new_root = _ET.fromstring(snap)
        except Exception:
            return
        if self.context:
            self.context.ditamap_root = new_root
            self._rebuild_preview()

    def _restore_selection(self, tref_list):
        # Reselect items corresponding to trefs after rebuild
        sel_items = []
        for item, tref in self._item_map.items():
            if tref in tref_list:
                sel_items.append(item)
        self.tree.selection_set(sel_items)
        if sel_items:
            self.tree.focus(sel_items[0])

    # ------------------------------------------------------------------
    # Journal replay helpers
    # ------------------------------------------------------------------

    def _find_tref_by_href(self, root: ET.Element, href: str):
        if not href:
            return None
        return root.xpath(f'.//topicref[@href="{href}"]')

    def _replay_edits(self):
        if self.context is None or self.context.ditamap_root is None:
            return
        root = self.context.ditamap_root
        for rec in self._edit_journal:
            op = rec.get("op")
            href = rec.get("href", "")
            matches = self._find_tref_by_href(root, href)
            if not matches:
                continue
            tref = matches[0]
            if op == "delete":
                parent = tref.getparent()
                if parent is not None:
                    parent.remove(tref)
            elif op == "move":
                direction = rec.get("dir")
                parent = tref.getparent()
                if parent is None:
                    continue
                siblings = list(parent)
                idx = siblings.index(tref)
                if direction == "up" and idx > 0:
                    parent.remove(tref)
                    parent.insert(idx - 1, tref)
                elif direction == "down" and idx < len(siblings) - 1:
                    parent.remove(tref)
                    parent.insert(idx + 1, tref)
                elif direction == "promote" and parent.tag == "topicref":
                    grand = parent.getparent()
                    if grand is not None:
                        pidx = list(grand).index(parent)
                        parent.remove(tref)
                        grand.insert(pidx + 1, tref)
                elif direction == "demote" and idx > 0:
                    left = siblings[idx - 1]
                    left.append(tref)

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
    # Debug utilities
    # ------------------------------------------------------------------
    def _dump_state(self):
        """Write a snapshot of key runtime state *and* full structure outline to the logger."""
        # Basic state summary
        log.debug(
            "STATE | depth=%s | excluded_styles=%s | selection=%s | undo=%d | redo=%d",
            self._depth_var.get(),
            getattr(self, "_excluded_styles", {}),
            list(self.tree.selection()),
            len(self._undo_stack),
            len(self._redo_stack),
        )

        # Dump complete outline of the current ditamap
        if self.context is None or self.context.ditamap_root is None:
            log.debug("OUTLINE | <no context loaded>")
            return

        outline_lines: list[str] = []

        def _walk(tref: ET.Element, level: int = 0):
            nav = tref.find("topicmeta/navtitle")
            title = nav.text.strip() if nav is not None and nav.text else "(untitled)"
            outline_lines.append("  " * level + f"- {title}")
            for child in [el for el in list(tref) if el.tag in ("topicref", "topichead")]:
                _walk(child, level + 1)

        _walk(self.context.ditamap_root, 0)
        log.debug("OUTLINE START\n%s\nOUTLINE END", "\n".join(outline_lines))
        """Write a snapshot of key runtime state to the logger."""
        log.debug(
            "STATE | depth=%s | excluded_styles=%s | selection=%s | undo=%d | redo=%d",
            self._depth_var.get(),
            getattr(self, "_excluded_styles", {}),
            list(self.tree.selection()),
            len(self._undo_stack),
            len(self._redo_stack),
        )

    def _start_debug_trace(self):
        """Attach a temporary rotating file handler capturing DEBUG for all loggers."""
        import os, datetime, logging, logging.handlers

        log.info("Debug trace button activated by user")
        log_dir = os.getenv("ORLANDO_LOG_DIR", "logs")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_path = os.path.join(log_dir, f"structure_trace_{ts}.log")

        handler = logging.handlers.RotatingFileHandler(
            trace_path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        try:
            from pythonjsonlogger import jsonlogger  # type: ignore
            handler.setFormatter(jsonlogger.JsonFormatter())
        except ImportError:
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.setLevel(logging.DEBUG)

        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

        # Also attach to this module logger and ensure it emits
        module_logger = logging.getLogger(__name__)
        module_logger.addHandler(handler)
        module_logger.setLevel(logging.DEBUG)

        log.info("==== StructureTab global debug trace started – writing to %s ====", trace_path)
        self._dump_state()

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