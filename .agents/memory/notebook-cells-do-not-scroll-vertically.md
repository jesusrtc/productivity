# Notebook cells do not scroll vertically

Notebook code and ordinary outputs should be fully visible or explicitly hidden,
never vertically scrollable inside a cell. Client-authored displayed HTML may
keep its own intentional scrolling. The interactive editor's highlighted source
owns its natural height; its textarea fills that height without contributing a
fixed rows/manual-resize height. Preserve the final empty source line when sizing
the highlight so typing, wrapping, and reopening hidden code never clip text.
