# Assistant series dates open on demand

The user's September 16, 2026 revision replaces the expanded series/date tree.
Keep the normal full-width Document tabs layout, including Index, nested tabs,
and the document-scoped +. Near the series name, show a small “More in this
series” button. Dates stay hidden until that button is clicked; the menu lists
notes newest date first, with unknown dates last. Selecting a date closes the
menu and opens that note with its own tabs. Escape and outside clicks dismiss
the menu. The series name still opens the overview.

Series membership is independent of the main list's workspace/search filters
and is stored in the root note's series metadata, not tab parent relationships.
Each note keeps its independent Markdown file. Standalone notes keep their
normal document tabs without a series button. Switching tabs and unchanged
polls preserve the current pane and rail; sibling edits preserve an open menu.
