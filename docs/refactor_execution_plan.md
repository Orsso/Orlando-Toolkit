# Structure Tab Refactor: Execution Plan

This document outlines the sequential, step-by-step plan for refactoring the `StructureTab` component. The plan is designed to be executed in phases, with mandatory **Human Approval Milestones** to ensure the implementation remains aligned with the project's goals and the rules defined in `structure_tab_refactor_plan.md`.

---

## Phase 1: Foundation - Core Logic & Service Layer (Headless)

**Goal**: To build and rigorously test the core business logic in complete isolation from the UI. This ensures the engine that powers the feature is correct before any UI is connected.

-   **Step 1.1: Create New Directory Structure**
    -   **Action**: Create the new package directories required by the proposed architecture:
        -   `orlando_toolkit/core/services/`
        -   `orlando_toolkit/ui/view_models/`
    -   **Verification**: The directories exist and contain `__init__.py` files.

-   **Step 1.2: Implement `StructureService`**
    -   **Action**: Create `orlando_toolkit/core/services/structure_service.py`. This class will encapsulate all Ditamap and topic manipulation logic.
    -   **Details**:
        -   Migrate and refactor all merging and consolidation logic from `orlando_toolkit/core/merge.py` into methods of this service.
        -   The service's methods will be GUI-agnostic, operating solely on the `DitaContext` model.
        -   **Critical Point**: The implementation must strictly adhere to all **Merging Logic Rules (FR6.1-FR6.4)** and **Orlando DITA Compliance Rules (A.1-C.4)** from the refactor plan.

-   **Step 1.3: Create a Rigorous Test Suite for `StructureService`**
    -   **Action**: Create `tests/core/services/test_structure_service.py`.
    -   **Details**:
        -   Write unit tests that cover every single merging and compliance rule.
        -   Create specific tests for edge cases: merging the first item, merging the last item, empty topics, etc.
        -   Each test will create an input `DitaContext`, pass it to a `StructureService` method, and assert that the output `DitaContext` is exactly as expected.

> ### **Milestone 1: Core Logic Validation (Human Approval Required)**
> -   **To Review**: The complete `StructureService` implementation and its associated unit test suite.
> -   **Goal**: To certify that the core business logic is correctly implemented and fully tested before proceeding. Your approval confirms that the engine is sound.
> -   **Proceed only when**: You have reviewed the code and confirmed that the tests are comprehensive and passing.

---

## Phase 2: State Management & Command Pattern (Headless)

**Goal**: To build the intermediary layer that manages application state and the undo/redo functionality.

-   **Step 2.1: Implement Command Pattern**
    -   **Action**: Create `orlando_toolkit/ui/view_models/commands.py`. This file will contain the base `Command` interface and concrete command classes (e.g., `MergeByLevelCommand`, `ManualMergeCommand`).
    -   **Details**: Each command object will encapsulate a request to the `StructureService`.

-   **Step 2.2: Implement `StructureViewModel`**
    -   **Action**: Create `orlando_toolkit/ui/view_models/structure_view_model.py`.
    -   **Details**:
        -   The ViewModel will hold the application state (`DitaContext`).
        -   It will manage the undo and redo stacks.
        -   It will have an `execute_command` method that runs a command, updates the state, and pushes the command onto the undo stack.
        -   It will expose the current Ditamap structure for the UI to render.

-   **Step 2.3: Create Test Suite for ViewModel and Commands**
    -   **Action**: Create `tests/ui/view_models/test_structure_view_model.py`.
    -   **Details**: Write unit tests to verify:
        -   Executing a command correctly modifies the `DitaContext`.
        -   The undo/redo stacks are managed properly.
        -   Calling `undo` reverts the state to its previous condition.

> ### **Milestone 2: State & Undo/Redo Validation (Human Approval Required)**
> -   **To Review**: The `StructureViewModel`, the command classes, and their unit tests.
> -   **Goal**: To certify that the state management and the entire undo/redo mechanism are functioning correctly in a headless environment.
> -   **Proceed only when**: You have reviewed the code and confirmed the tests are comprehensive and passing.

---

## Phase 3: UI Refactoring and Final Integration

**Goal**: To replace the old UI with a new, clean implementation that delegates all logic to the ViewModel.

-   **Step 3.1: Create `NewStructureTab`**
    -   **Action**: Create a new file, `orlando_toolkit/ui/new_structure_tab.py`. We will build the new UI here to avoid breaking the application during development.
    -   **Details**: This class will be a "dumb" component. It will:
        -   Instantiate the `StructureViewModel`.
        -   Render the UI based on data from the ViewModel.
        -   Delegate all user input (button clicks, etc.) to the ViewModel by creating and executing command objects.

-   **Step 3.2: Integrate `NewStructureTab` into the Application**
    -   **Action**: Modify `orlando_toolkit/app.py` to instantiate `NewStructureTab` instead of the old `StructureTab`.

> ### **Milestone 3: Functional UI Test (Human Approval Required)**
> -   **To Review**: The running application with the `NewStructureTab` integrated.
> -   **Goal**: To perform a full, end-to-end functional test of all features defined in the refactor plan (merging, undo/redo, search, etc.).
> -   **Proceed only when**: You have confirmed that all features work as expected and the UI is responsive and correct.

---

## Phase 4: Cleanup and Finalization

**Goal**: To satisfy the "Definition of Done" by removing all legacy code.

-   **Step 4.1: Deprecate and Remove Old Code**
    -   **Action**: Delete the following files:
        -   `orlando_toolkit/ui/structure_tab.py`
        -   `orlando_toolkit/core/merge.py`
        -   `tests/core/test_merge.py`
    -   **Action**: Rename `new_structure_tab.py` to `structure_tab.py`.

-   **Step 4.2: Final Code Review**
    -   **Action**: Perform a final review of the entire refactored codebase.
    -   **Details**: Check for any remaining dead code, ensure documentation and comments are up-to-date, and confirm that the project's coding standards are met.

> ### **Milestone 4: Refactor Complete (Final Human Approval)**
> -   **To Review**: The final state of the codebase.
> -   **Goal**: To officially declare the refactoring complete, satisfying the **Definition of Done**.
> -   **Proceed only when**: You are fully satisfied with the result.
