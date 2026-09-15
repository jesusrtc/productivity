# Command-click a notebook cell to expand it

Command-click replaces double-click for opening a saved notebook cell in the
existing file modal. It works across headers, editable or rendered code, and
results, including nested controls. Capture the click on the notebook so the
shortcut opens the cell without also running the clicked control's action.
Ordinary clicks and double-clicks retain their native editing/selection behavior;
the explicit Expand button remains available. Skip unsaved drafts and cells
already inside the modal, and preserve the stable cell ID and repository root.

This supersedes `notebook-cell-double-click-expands.md`.
