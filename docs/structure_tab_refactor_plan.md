# Functional Specification: Structure Tab

This document defines the user-facing features and business rules for the Structure Tab. It serves as the definitive guide for the refactoring effort, ensuring that all existing capabilities are preserved and improved upon.

## I. Functional Requirements

### 1. Structure Preview

-   **FR1.1**: The system must display a hierarchical tree view representing the document's topic structure.
-   **FR1.2**: Each item in the tree must display the corresponding topic's title.
-   **FR1.3**: The hierarchy must clearly show parent-child and sibling relationships between topics.

### 2. Automatic Structure Generation & Real-time Updates

-   **FR2.1**: The initial topic structure shall be generated automatically based on the headings in the source document.
-   **FR2.2**: The user must be able to control this generation using the rules below. The structure preview must update in real-time to reflect any changes to these rules.

-   **FR2.3 - Rule: Topic Splitting by Heading Level**
    -   The user must be able to define a "maximum heading level" (an integer from 1 to 9).
    -   Any heading at or numerically lower than this level (e.g., level 1, 2, 3 if the max is 3) shall start a new topic.
    -   Any heading at a numerically higher level shall be treated as content within its parent topic, not as a new, separate topic.

-   **FR2.4 - Rule: Topic Merging by Heading Style**
    -   The system must identify and present the user with a list of all paragraph styles used for headings in the source document.
    -   The user must be able to select one or more of these styles to be "excluded."
    -   Any heading formatted with an excluded style shall not start a new topic but will be merged into its parent topic.

### 3. Manual Structure Editing

-   **FR3.1**: The user must be able to manually modify the topic hierarchy.

-   **FR3.2 - Action: Cut & Paste**
    -   The user must be able to select a single topic in the tree and "cut" it.
    -   Cutting a topic also cuts all of its descendant topics.
    -   The user must be able to select another topic and "paste" the cut topic (and its descendants) as a sibling or child of the selected topic.

-   **FR3.3 - Action: Undo & Redo**
    -   The user must be able to undo any structural modification (e.g., a paste operation, a change in heading level, etc.).
    -   The user must be able to redo any action that has been undone.
    -   The system should support a multi-level undo/redo history.

### 4. Persistence of Manual Edits

-   **FR4.1**: All manual edits (e.g., cut-and-paste operations) must be preserved even when the automatic structure generation rules are changed.
-   **Example**: If a user moves Topic A to be a child of Topic Z, and then changes the max heading level, Topic A must remain a child of Topic Z in the newly generated structure.

### 5. UI Helpers & Utilities

-   **FR5.1 - Search**: The user must be able to search for topics by title. The system should highlight and navigate to matching topics in the tree.
-   **FR5.2 - Status Notifications**: The system must provide clear, temporary status messages for actions (e.g., "Topic pasted successfully," "Nothing to undo.").
-   **FR5.3 - Content Preview**: The user must be able to select a topic in the tree and preview its rendered content in an external browser window.

### 6. Merging Logic Engine

-   **FR6.1 - Rule: Idempotency**: Applying the same set of merging rules multiple times to an original, unmodified document structure must produce the exact same result as applying them once. The engine's operations must be stateless.
-   **FR6.2 - Rule: Order of Operations**: Merging operations must be applied in a consistent, defined order to ensure predictable outcomes. The proposed order is: 1) Depth-based merging, 2) Style-based merging, 3) Final consolidation.

-   **FR6.3 - Rule: Merge Behavior & Content Preservation**:
    -   **Never Lose Content**: All block-level content (`<p>`, `<ul>`, `<table>`, etc.) from a source topic must be moved to the destination topic. No content shall be discarded.
    -   **Preserve Titles from Style-Based Merges**: When a topic is merged because its heading style is excluded, its title text must be preserved. It shall be converted into a new `<p>` element and inserted at the beginning of the content that is moved to the destination topic.
    -   **Discard Titles from Depth-Based Merges**: When a topic is merged because it exceeds the depth limit, its title is considered a sub-heading and is discarded. The content is moved directly under the parent topic.
    -   **Define Merge Target**: The destination for merged content is the nearest valid preceding topic at the same or higher level. If no preceding topic exists, it is merged into the direct parent.
    -   **Ensure ID Uniqueness**: All `@id` attributes within the moved content block must be regenerated to ensure they are unique within the document. Any internal references (`@href`, `@conref`) within that block must be updated to point to the new IDs.

-   **FR6.4 - Rule: Consolidation**: After all other merging rules are applied, the engine must perform a final consolidation pass. This pass promotes any topic that is the sole child of a container (`<topichead>`), effectively removing the redundant container.

---

## II. Orlando DITA Compliance Rules

Analysis of the reference DITA archive has revealed a set of strict structural and syntactical rules that must be followed to ensure output compatibility. The refactored system must adhere to the following rules.

### 1. Core File Structure
-   **Rule A.1 - Core Directory Layout**: The structure manipulation logic must operate on the principle that the Ditamap resides at the root of the `DATA` directory and all topic files reside in a `topics/` subdirectory. Other directories (e.g., `media/`, `dtd/`) are outside the scope of this refactor.
-   **Rule A.2 - Topic Filenames**: Topic filenames must be generated based on a unique ID (e.g., `_SVC-BEOPS.PROCBEO001.dita_orl008590.dita`).

### 2. Ditamap Structure (`.ditamap`)
-   **Rule B.1 - Use `<topichead>` for Structural Headings**: Headings that serve as organizational containers and do not link to a content file must be generated as `<topichead>` elements.
-   **Rule B.2 - Use `<topicref>` for Content Links**: Headings that represent actual content must be generated as `<topicref>` elements with an `href` attribute pointing to the corresponding topic file.
-   **Rule B.3 - Mandatory `locktitle="yes"`**: Every `<topicref>` element must include the attribute `locktitle="yes"`.
-   **Rule B.4 - Ditamap Metadata**: Every `<topichead>` and `<topicref>` must contain a `<topicmeta>` element which, in turn, contains:
    -   A `<navtitle>` with the topic's title.
    -   A `<critdates>` element with `<created>` and `<revised>` dates.
    -   An `<othermeta name="tocIndex" content="..."/>` element to define the precise table of contents numbering (e.g., "1.1", "2.3.4").

### 3. Topic File Structure (`.dita`)
-   **Rule C.1 - Default Topic Type is `<concept>`**: All generated topic files must use `<concept>` as their root element.
-   **Rule C.2 - Universal Unique IDs**: Every single element within a topic file (including `<title>`, `<prolog>`, `<p>`, `<ul>`, `<li>`, etc.) must have a unique `id` attribute, preferably a generated UUID.
-   **Rule C.3 - Internal Prolog Metadata**: Each topic must contain a `<prolog>` element immediately after the `<title>`. This prolog must contain its own `<critdates>` and `<metadata>` elements.

---

## III. Proposed Architecture

To address the challenges outlined above and adhere to the project's architectural principles, we propose the following structure.

### 1. `StructureService` (New Component)

-   **Location**: `orlando_toolkit/core/services/structure_service.py`
-   **Responsibility**: This new, GUI-agnostic service will encapsulate all business logic related to `ditamap` manipulation. It will be the single source of truth for applying structural rules.
-   **Proposed API**:
    -   `apply_rules(context: DitaContext, rules: StructureRules) -> DitaContext:` This method will take the current context and a set of rules (e.g., a dataclass containing `max_depth` and `excluded_styles`) and return a new context with the rules applied.
    -   This service will contain the logic currently found in `core.merge`.

### 2. `StructureViewModel` / `StructureManager` (New Component)

-   **Location**: `orlando_toolkit/ui/view_models/structure_view_model.py` (A new `view_models` sub-package should be created).
-   **Responsibility**: This class will act as the intermediary between the UI (`StructureTab`) and the `StructureService`. It will manage the application state for the structure view.
-   **Core Duties**:
    -   Hold the `DitaContext`.
    -   Manage the undo/redo stack using the **Command Pattern**.
    -   When a user action occurs, it will create a command object, execute it (which involves calling the `StructureService`), and update the undo stack.
    -   Provide the UI with the data it needs to render the tree.

### 3. `StructureTab` (Refactored Component)

-   **Location**: `orlando_toolkit/ui/structure_tab.py`
-   **Responsibility**: The refactored `StructureTab` will be a "dumb" component, responsible only for UI rendering and user input.
-   **Core Duties**:
    -   Build the visual widgets (Treeview, buttons, etc.).
    -   Delegate all user actions (e.g., button clicks, spinbox changes) to the `StructureViewModel`.
    -   Observe the `StructureViewModel` for changes and update the `Treeview` display accordingly.

---

## IV. Key Challenges & Refactoring Goals

1.  **Separation of Concerns**:
    -   **Problem**: `StructureTab` is a monolith, mixing UI code, complex state management (undo stacks, clipboard), and business logic orchestration.
    -   **Goal**: Decompose the class. Create a dedicated `StructureManager` or `StructureViewModel` to handle state and logic, leaving the `StructureTab` responsible only for rendering the UI and delegating user actions.

2.  **Performance**:
    -   **Problem**: The undo/redo system's reliance on `copy.deepcopy()` for every change is highly inefficient and will cause significant UI lag with large documents.
    -   **Goal**: Replace the snapshot-based undo system with a **Command Pattern**. Each action (e.g., `CutCommand`, `PasteCommand`, `ChangeDepthCommand`) will be an object that knows how to `execute()` and `undo()` its own operation. This is far more memory and CPU efficient.

3.  **Robustness & State Management**:
    -   **Problem**: The current system of managing state with multiple `DitaContext` copies (`context`, `_orig_context`) and replaying a journal is complex and prone to bugs.
    -   **Goal**: Centralize state management in the new `StructureManager`. This class will be the single source of truth. It will hold the `ditamap_root` and apply operations to it, making the flow of data much clearer.

4.  **Readability & Maintainability**:
    -   **Problem**: The current code is dense and difficult to follow due to its monolithic nature.
    -   **Goal**: Produce clean, well-documented, and testable code. The separation of concerns will naturally lead to smaller, more focused classes and methods that are easier to understand and maintain.

5.  **Definition of Done**:
    -   **Goal**: The refactoring is complete only when the new system is fully integrated, all legacy code related to the old `StructureTab` logic has been removed, and there is no unused or duplicated logic. The final result must be a clean, seamless replacement of the old system.
