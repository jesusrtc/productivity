# Markdown tables align editable cells

The user wants pipe tables to render as tables in the Markdown editor, including
the screenshot's header/separator column-count mismatch. Tolerate that mismatch
in both the Lezer editor parser and the shared Marked renderer without rewriting
stored Markdown. Use shared columns, wrapping cells, visible headers, native
cell editing, and explicit empty cells. CodeMirror's replacement buffers consume
grid positions: assign each real cell its column and row explicitly. Its normal
coordinate lookup assumes flowing text; use browser caret coordinates and
posAtDOM for mouse selection in independently wrapped table cells.
