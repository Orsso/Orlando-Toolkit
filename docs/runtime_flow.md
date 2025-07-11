# Runtime Flow

📖 **[← Back to Architecture Overview](./architecture_overview.md)**

```mermaid
sequenceDiagram
    participant User
    participant GUI
    participant Service
    participant Converter
    participant Merge as "Merge Engine"
    participant Preview as "Preview System"
    participant FS as "File System"

    User->>GUI: "Select DOCX"
    GUI->>Service: "convert(path, metadata)"
    Service->>Converter: "convert_docx_to_dita()"
    Converter-->>Service: "DitaContext"
    Service-->>GUI: "context ready"
    
    Note over GUI: Load three-tab interface
    GUI->>GUI: "Setup Metadata/Images/Structure tabs"
    
    User->>GUI: "Configure Metadata (Tab 1)"
    GUI->>GUI: "Update context metadata"
    
    User->>GUI: "Review Images (Tab 2)"
    GUI->>GUI: "Configure image naming"
    
    User->>GUI: "Adjust Structure (Tab 3)"
    GUI->>GUI: "Set topic depth & exclusions"
    GUI->>Merge: "merge_topics_unified()"
    Merge-->>GUI: "Updated context"
    GUI->>Preview: "render_html_preview()"
    Preview-->>GUI: "Real-time structure preview"
    
    User->>GUI: "Structural editing (move/rename)"
    GUI->>GUI: "Apply structural changes"
    GUI->>Preview: "Update preview"
    Preview-->>GUI: "Refreshed preview"
    
    User->>GUI: "Click Generate Package"
    GUI->>Service: "prepare_package()"
    Service->>Merge: "Apply final merge rules"
    Merge-->>Service: "Optimized context"
    Service->>FS: "save temp dir"
    Service-->>GUI: ".zip ready"
    GUI-->>User: "Save dialog"
```

## Workflow Details

### 1. Document Loading
- User selects DOCX file through file dialog
- Conversion service performs initial DOCX → DITA transformation
- GUI transitions from home screen to three-tab interface

### 2. Three-Tab Configuration
**Metadata Tab**
- Configure document title, manual code, revision date
- Set Orlando-specific metadata properties
- Changes propagate to other tabs via callbacks

**Images Tab**
- Preview all extracted images with thumbnails
- Configure naming prefixes and conventions
- Real-time filename preview with section-based numbering

**Structure Tab**
- Set maximum topic depth (1-9 levels)
- Configure style exclusions at different heading levels
- Real-time merge preview shows final document structure
- Structural editing with move/promote/demote operations
- Search and filter capabilities
- XML preview for individual topics

### 3. Real-Time Processing
- All structural changes are applied immediately to a working copy
- Preview system renders HTML using embedded XSLT transforms
- Merge engine applies depth and style rules in unified single-pass
- Undo/redo support for all structural modifications

### 4. Package Generation
- Final merge rules applied based on current configuration
- Topics and images renamed with stable identifiers
- Self-contained ZIP archive generated without embedded DTDs
- DOCTYPE declarations use simple filenames for catalog compatibility

### 5. Error Handling
- Conversion errors shown via message boxes
- Background operations use progress indicators
- Logging system provides detailed debugging information

