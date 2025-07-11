# orlando_toolkit.ui

Tkinter widgets used by the desktop app.

📖 **[← Back to Architecture Overview](../../docs/architecture_overview.md)**

## Tabs

* **MetadataTab** – Edit manual metadata including document title, code, and revision information.
* **ImageTab** – Preview and rename extracted images with automatic section-based naming.
* **StructureTab** – Configure topic depth, preview document structure, and perform structural editing operations.

## Components

`custom_widgets.py` provides reusable frames (toggle, thumbnail).
`dialogs.py` provides centered dialog utilities for consistent UI placement.

## Architecture

This layer contains only presentation code; all processing happens in `ConversionService`. The UI follows a tab-based workflow:

1. **Metadata Tab**: Configure document metadata and revision tracking
2. **Images Tab**: Manage image naming and preview extracted graphics
3. **Structure Tab**: Control topic hierarchy, perform real-time merging, and preview the final document structure

Each tab operates on a shared `DitaContext` object and can trigger updates to other tabs through callback mechanisms. 