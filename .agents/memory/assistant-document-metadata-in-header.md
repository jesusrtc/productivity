# Assistant document metadata belongs in the header

On September 15, 2026 the user requested that tasks and notes reserve the main
document pane for content. Do not prepend large titles, TLDR blocks, metadata
cards, badges, or workspace paths to the document body.

Keep a small title and quiet editable properties in the top bar. Tasks expose
status, priority, a native Due calendar, and Repeats; meeting notes expose a
date calendar and workspace-local series. Additional properties and read-only
context live in a compact details menu. Related meeting content uses its
parent meeting's properties and raw notes remain unchanged.

Human edits through the header are explicitly authorized. The single-property
API keeps existing task completion rules, validates dates/series/recurrence,
and rejects stale field values. Preserve the current document's identity when
navigating or saving; updates must not reopen a closed modal.
