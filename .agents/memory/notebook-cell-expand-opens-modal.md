# Notebook cell Expand opens the file modal at that cell

Notebook cell headers offer an expand button beside Pin code. Open the existing
file modal with the same notebook path and repository/worktree root, carrying
the cell's stable ID and an index fallback. The explicit target takes priority
over remembered reading position and reveals hidden code without changing the
global hide-code setting. Markdown cells can expand too; unsaved draft cells
cannot. Hide the expand button inside the already expanded modal, and keep the
underlying notebook's expand handler usable after closing the modal.
