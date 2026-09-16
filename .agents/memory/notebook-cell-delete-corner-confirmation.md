# Notebook cell deletion stays visible and asks for confirmation

Editable notebook cells have a trash button in the upper-right corner, outside
the collapsible header so it remains available in output-only mode. Code,
Markdown, raw text, and draft cells all ask for confirmation before removal;
Cancel leaves the cell untouched. Running cells disable deletion. Persisted
deletions retain the owning vault and prefer the stable cell ID. Read-only
repository previews remain read-only.
