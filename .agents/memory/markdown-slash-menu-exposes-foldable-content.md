# Markdown slash menu exposes foldable content

The user wants Notion-style `/` commands for Markdown block actions, including
the existing safe HTML folds. In an editable document, `/` on an empty line
opens a searchable menu; arrows, Enter, native click, and Escape control it.
Foldable content is first and `/fold` or `/toggle` finds it. It inserts native
details/summary tags with blank Markdown boundaries and selects the title.
Keep ordinary slashes and code untouched, retain focus while choosing, and
make each insertion one undo step. Headings, lists, tasks, quotes, code,
tables, and dividers share the menu. Existing save and disclosure-copy
behavior remains covered by the native editor integration tests.
