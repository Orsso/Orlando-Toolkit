# -*- coding: utf-8 -*-
"""
Custom Tkinter widgets for the Orlando Toolkit UI.
Reusable UI components and specialized controls.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# ----------------------------------------------------------------------
# Generic tooltip helper
# ----------------------------------------------------------------------

class ToolTip(tk.Toplevel):
    """A simple tooltip window that appears near the cursor.

    Usage::
        tip = ToolTip(parent_widget)
        tip.show("Some text", x_root, y_root)
        tip.hide()

    The tooltip is *overrideredirect* so it has no window chrome.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Start hidden
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.label = ttk.Label(
            self,
            text="",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padding=(4, 2),
            justify="left",
        )
        self.label.pack()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def show(self, text: str, x: int, y: int):
        """Display *text* at screen coordinates *(x, y)*."""
        self.label.config(text=text)
        # Small offset so we don't cover the mouse pointer
        self.geometry(f"+{x + 20}+{y + 15}")
        self.deiconify()

    def hide(self):
        """Hide the tooltip if it is visible."""
        self.withdraw()


class ToggledFrame(tk.Frame):
    """A collapsible container that can show or hide its content."""

    def __init__(self, parent, text: str = "", *args, **options):
        super().__init__(parent, *args, **options)

        self.text = text
        self.columnconfigure(1, weight=1)

        self.toggle_button = ttk.Checkbutton(self, width=2, text="+", command=self.toggle, style="Toolbutton")
        self.toggle_button.grid(row=0, column=0, sticky="ns")
        self.title_label = ttk.Label(self, text=text)
        self.title_label.grid(row=0, column=1, sticky="ew")

        self.sub_frame = tk.Frame(self)
        self.sub_frame.grid(row=1, column=1, sticky="nsew")
        self.sub_frame.grid_remove()  # Start folded

        self.toggle_button.invoke()  # Start folded

    def toggle(self):
        if self.sub_frame.winfo_viewable():
            self.sub_frame.grid_remove()
            self.toggle_button.configure(text="+")
        else:
            self.sub_frame.grid()
            self.toggle_button.configure(text="-")


class Thumbnail(tk.Frame):
    """A widget that displays an image thumbnail and its filename."""

    def __init__(self, parent, image_path: str, filename: str, size: tuple[int, int] = (150, 150)):
        super().__init__(parent, borderwidth=1, relief="solid")
        self.image_path = image_path
        self.filename = filename
        self.size = size
        self.selected = False

        self.image_label = ttk.Label(self)
        self.image_label.pack()

        self.label = ttk.Label(self, text=filename, wraplength=size[0])
        self.label.pack(fill="x", padx=5, pady=5)

        self.photo_image: ImageTk.PhotoImage | None = None
        self.load_image()

    def load_image(self):
        try:
            with Image.open(self.image_path) as img:
                img.thumbnail(self.size)
                self.photo_image = ImageTk.PhotoImage(img)
                self.image_label.config(image=self.photo_image)
        except Exception as e:
            # Display placeholder on failure
            self.image_label.config(text=f"Error\n{e}", relief="solid", width=20, height=10)

    # --- Selection helpers -------------------------------------------------

    def select(self):
        self.selected = True
        self.config(relief="sunken", bg="lightblue")
        self.label.config(bg="lightblue")

    def deselect(self):
        self.selected = False
        self.config(relief="solid", bg="")
        self.label.config(bg="")

    def toggle_selection(self) -> bool:
        if self.selected:
            self.deselect()
        else:
            self.select()
        return self.selected 