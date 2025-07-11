# orlando_toolkit.core

Core processing layer used by all front-end interfaces.

📖 **[← Back to Architecture Overview](../../docs/architecture_overview.md)**

## What lives here?

* `models.py` – dataclasses like `DitaContext` that travel through the pipeline.
* `parser/` – low-level helpers to walk a Word document and pull out stuff.
* `converter/` – core DOCX ➜ DITA logic (pure functions, no I/O).
* `generators/` – small XML builders (tables etc.) so the converter stays readable.
* `services/` – high-level API (`ConversionService`) that the GUI / CLI call into.
* `merge.py` – advanced topic merging with depth limits and style exclusions.
* `preview/` – XML compilation and HTML rendering for real-time preview.
* `utils.py` – misc. helpers (slugify, XML save, colour mapping…).

## Key Modules

### Conversion Pipeline
- **converter/docx_to_dita.py**: Main conversion entry point
- **converter/structure_builder.py**: Two-pass conversion with role determination
- **converter/helpers.py**: Shared formatting and content processing utilities

### Advanced Processing
- **merge.py**: Unified topic merging engine supporting:
  - Depth-based merging (topics beyond specified level)
  - Style-based exclusions (exclude specific Word styles)
  - Smart content module creation
  - Single-pass processing to prevent content loss

### Preview System
- **preview/xml_compiler.py**: Real-time preview capabilities:
  - Raw XML extraction from `DitaContext`
  - HTML rendering with embedded XSLT transforms
  - Image embedding as data URIs for offline viewing
  - Browser-compatible output for structure validation

### Data Models
- **models.py**: Core data structures including `DitaContext` and `HeadingNode`

## Architecture Principles

Core modules should remain **I/O-free** and unit-testable; filesystem operations belong in `services`. The core layer provides pure functions that transform data without side effects, enabling reliable testing and reuse across different interfaces (GUI, CLI, API).