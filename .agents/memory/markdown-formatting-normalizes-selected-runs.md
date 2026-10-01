# Markdown formatting normalizes selected runs

The user wants Markdown formatting to toggle the whole selection: remove a
format when all selected visible text has it, otherwise remove its individual
selected delimiters and apply one span per Markdown block. A second click
removes that format. Preserve other inline styles, literal markers in code,
and formatted fragments outside a partial selection. Commands are single undo
steps. Native desktop and narrow-screen checks cover these cases in
core/tests/test_frontend_word_markdown.py.
