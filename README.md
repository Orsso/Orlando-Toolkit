# ![Orlando Toolkit](https://github.com/user-attachments/assets/15f610f5-52c0-43c3-93fc-37ae5be11d13) Orlando Toolkit

**Convert Word documents to DITA archives for Orlando**

---

## Overview

Orlando Toolkit converts Microsoft Word (.docx) files into DITA archives that comply with Orlando specifications. The tool preserves document structure, formatting, images, and tables while generating the required XML markup and metadata.

### Key Features

- **DOCX to DITA conversion** – Processes text, formatting, images, tables, and lists
- **Orlando compliance** – Follows Orlando-specific DITA conventions and DTD requirements
- **Automatic image handling** – Extracts every embedded picture and normalises all formats to **PNG** for 100 % preview fidelity
- **Depth-aware topic merging** – Collapse deep hierarchies with one click; deeper topics are merged into their parent so no information is lost (toggle-able in the *Structure* tab)
- **Metadata configuration** – User-friendly interface for manual properties and revision tracking
- **Package generation** – Creates complete ZIP archives ready for Orlando import

## Recent highlights

* **Word-consistent heading detection** – Parser now respects Word's outline-level inheritance.
* **Real-time depth merge** – Live preview shows exactly what the final ZIP will contain; enable/disable with a checkbox.
* **PNG image normalisation** – WMF/EMF and other exotic formats are converted to PNG to ensure consistent rendering.
* **One-click Python install in `build.bat`** – If Python 3.13 is missing, the build script installs it silently via `winget`.

---

## Getting Started

### Option 1: Pre-built Executable (Windows)

1. Download the latest `OrlandoToolkit.exe` from the **Releases** section
2. Run the executable directly - no installation required
3. Compatible with Windows 10/11

### Option 2: Run from Source

**Requirements:** Python 3.13+ (Windows/macOS/Linux)


```bash
# Clone and setup
git clone https://github.com/Orsso/orlando-toolkit
cd orlando-toolkit
python -m pip install -r requirements.txt

# Launch application
python run.py
```

### Option 3: Build Executable

> ⚠️ On Windows the provided `build.bat` will silently install Python 3.13 via **winget** if it is not detected, so you can run the build out-of-the-box.

```bash
# Windows
build.bat

```

---

## Usage

1. **Load Document** - Select your Word (.docx) file
2. **Configure Metadata** - Set manual title, codes, and revision information
3. **Review Images** - Adjust image naming and organization
4. **Configure Structure** - Set topic depth, preview hierarchy, and perform structural editing
5. **Generate Package** - Export complete DITA archive as ZIP

The application provides three main tabs for comprehensive document control:

- **Metadata Tab**: Configure document properties, revision tracking, and Orlando-specific metadata
- **Images Tab**: Preview extracted images, configure naming conventions, and manage graphics
- **Structure Tab**: Control topic hierarchy depth, preview document structure in real-time, and perform advanced structural editing operations

**Output Structure:**
- `DATA/topics/` - DITA concept files
- `DATA/media/` - Extracted images and assets
- Root ditamap with proper Orlando metadata

---

## Technical Details

### Architecture
```
orlando_toolkit/
├── core/              # Conversion engine
│   ├── converter/     # DOCX to DITA transformation
│   ├── parser/        # Document analysis and extraction
│   ├── generators/    # DITA XML builders
│   ├── services/      # High-level conversion orchestration
│   ├── merge.py       # Advanced topic merging engine
│   └── preview/       # Real-time XML compilation and rendering
└── ui/                # Tkinter GUI components
    ├── metadata_tab.py  # Document metadata configuration
    ├── image_tab.py     # Image management interface
    └── structure_tab.py # Topic hierarchy and structural editing

```

### Advanced Features

**Topic Merge Engine**
- Depth-based topic consolidation (configurable 1-9 levels)
- Style-based exclusions for fine-grained control
- Real-time preview of final document structure
- Unified merge algorithm prevents content loss

**Structural Editing**
- Interactive tree view with move/promote/demote operations
- Search and filter capabilities within document structure
- Undo/redo support for all structural modifications
- Heading filter to exclude specific Word styles

**Preview System**
- Real-time XML compilation and HTML rendering
- Browser-based preview with embedded images
- Raw XML inspection for validation and debugging

### Supported Elements
- Paragraphs with alignment and styling
- Ordered and unordered lists
- Tables with formatting preservation
- Inline formatting (bold, italic, underline)
- Color coding (red, green, blue, amber, cyan, yellow)
- Background highlighting
- Hyperlinks and cross-references
- Embedded images

---

For detailed architecture documentation, see **[Architecture Overview](docs/architecture_overview.md)**.

