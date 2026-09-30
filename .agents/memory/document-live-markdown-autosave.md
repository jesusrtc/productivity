# Current document tabs use live Markdown and idle autosave

The user wants Obsidian-style editing immediately when a Markdown document tab
opens: inactive blocks render inline and the active block exposes source. Only
the tab selected through the UI mounts an editor. Keep Markdown as the source,
native undo, content copying, drafts, metadata, and independent sibling bodies.

Autosave after 10 seconds without typing, show a saved timestamp, and save the
outgoing tab on UI navigation/close. Keep typing enabled during writes; advance
the saved baseline only to submitted text and preserve any newer draft. Stop
automatic retries after a conflict or failure. Respect newer navigation and
editor activity across asynchronous reads/writes.

Revert can discard unsaved edits or restore one of the latest 20 persisted
pre-save bodies for the current tab. History survives reloads and restores
compare the current saved body before writing. Restore content only, preserving
metadata and sibling tabs. This supersedes explicit-save-only defaults in
assistant-note-content-editing.md. Original captured text and Index/Dashboard
remain reading surfaces; the live editor bundle loads only on editable content.
