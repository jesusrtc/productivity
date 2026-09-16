# Notes have explicit content editing and draft markers

Notes in Assistant's document panels can be edited with Edit/Preview and an
explicit Save button. Use subtle amber line marks for pending content changes
and a small unsaved dot on the affected document tab. Saving clears the marks.
Keep drafts when switching tabs or closing/reopening the document; warn before
leaving the page with unsaved changes. Background refresh must preserve drafts
and selection. Original captured notes stay immutable.

Content saves compare the original body, reread the containing Markdown file,
and preserve metadata and sibling subtabs. Reject stale drafts without losing
the user's text. Keep the Markdown body as the source of truth.
