# EMDX TUI Refactoring Plan

## Problem Analysis
The textual_browser.py file has grown to 3,097 lines with 6 classes, making it difficult to maintain. The file contains:

### Current Classes (line numbers):
- SelectionTextArea (line 66) - Text selection functionality
- TitleInput (line 116) - Input field for editing titles
- VimEditTextArea (line 149) - Vim-like editing capabilities  
- FullScreenView (line 654) - Full-screen document viewer
- DeleteConfirmScreen (line 805) - Modal confirmation dialog
- MinimalDocumentBrowser (line 870) - Main application class

## Proposed Refactoring Structure

All components will remain under `emdx/ui/` for clean organization:

### 1. Widget Components: `emdx/ui/`
Extract specialized text input and editing widgets:

**File: `emdx/ui/text_areas.py`**
- SelectionTextArea - Text selection with mouse/keyboard
- VimEditTextArea - Full vim modal editing implementation
- All vim mode logic, key bindings, and state management

**File: `emdx/ui/inputs.py`**  
- TitleInput - Specialized input for document title editing
- Any other custom input widgets

### 2. Screen Components: `emdx/ui/`
Extract modal screens and full-screen views:

**File: `emdx/ui/document_viewer.py`**
- FullScreenView - Full-screen document viewing with navigation
- Document rendering logic and key bindings

**File: `emdx/ui/modals.py`**
- DeleteConfirmScreen - Delete confirmation modal
- Future modal dialogs (tag editing, settings, etc.)

### 3. Browser Components: `emdx/ui/`
Split the massive main browser class:

**File: `emdx/ui/main_browser.py`**
- MinimalDocumentBrowser (core app logic only)
- App initialization and high-level coordination

**File: `emdx/ui/document_actions.py`**
- Document CRUD operations (view, edit, delete, restore)
- Tag management actions
- Claude execution logic

**File: `emdx/ui/navigation.py`**
- Search functionality and filtering
- Document list navigation
- Mode switching (NORMAL, SEARCH, LOG_BROWSER)

**File: `emdx/ui/execution_browser.py`**
- Execution log browsing functionality
- Log file handling and display
- Execution status tracking

### 4. Shared Utilities: `emdx/ui/`
**File: `emdx/ui/mixins.py`**
- Common functionality shared across components
- Event handling patterns
- State management helpers

**File: `emdx/ui/constants.py`**
- Key binding definitions
- CSS styles
- Configuration constants

## Migration Strategy - Pure Lift and Shift

**Critical Principle: ZERO functional changes. Only move code, update imports.**

### Phase 1: Extract Widgets (Low Risk)
1. Create `emdx/ui/text_areas.py`
2. Copy SelectionTextArea and VimEditTextArea classes exactly as-is
3. Create `emdx/ui/inputs.py` and copy TitleInput exactly as-is
4. Update imports in textual_browser.py only
5. Test that everything works identically

### Phase 2: Extract Screens (Medium Risk)  
1. Create `emdx/ui/document_viewer.py` and copy FullScreenView exactly as-is
2. Create `emdx/ui/modals.py` and copy DeleteConfirmScreen exactly as-is
3. Update imports in textual_browser.py only
4. Test that modal and full-screen work identically

### Phase 3: Split Main Browser (High Risk)
1. Copy MinimalDocumentBrowser class to `emdx/ui/main_browser.py` exactly as-is
2. Update `textual_browser.py` to import and re-export MinimalDocumentBrowser
3. Maintain 100% backward compatibility
4. Test that all functionality works identically

### Phase 4: Clean Up
1. Remove extracted classes from textual_browser.py
2. Keep textual_browser.py as import aggregator for backward compatibility
3. No refactoring, no improvements, no optimizations

## Benefits

### Maintainability
- Single responsibility principle for each file
- Easier to locate and modify specific functionality
- Reduced cognitive load when working on features

### Testability
- Isolated components easier to unit test
- Mock dependencies more easily
- Test specific functionality without full app

### Extensibility
- Add new widgets without touching main browser
- Easier to add new modal screens
- Plugin-like architecture for new features

### Performance
- Smaller import graphs
- Potential for lazy loading of heavy components
- Better code organization for bundling

## Implementation Notes

### Import Strategy
- Use relative imports within packages
- Maintain clean public APIs for each module
- Consider __init__.py files for convenient imports

### Backward Compatibility
- Maintain exact same public interface
- No deprecation warnings - everything works exactly as before
- Zero breaking changes to CLI integration
- textual_browser.py continues to work as main entry point

### Testing Strategy
- Test after each phase that functionality is 100% identical
- No new tests needed - existing behavior must be preserved
- Manual testing of all TUI features after each extraction

This refactoring will transform a 3,097-line monolith into organized, maintainable files while preserving 100% identical functionality through pure lift-and-shift moves.