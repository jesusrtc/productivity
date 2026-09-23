# Linked documents open in the main file area

User preference: terminal pills must not repeat a blue document-link badge.
Select documents from the sidebar instead. Workspace Documents and Assistant
Linked documents both highlight the selected terminal's containing document;
explicit terminal clicks also open the document inline; background refreshes
only update the highlight. Assistant's
list is derived from saved terminal links, deduplicated by database/document ID,
including stopped terminals, without inspecting or starting tmux.

Sidebar document clicks use the existing Assistant editor and document tabs in
the main file area. Keep Files at its user-selected visibility; toggling it while
the document is open persists normally. Closing, expanding, or navigating
away must not restore an older visibility. Expand retains the same editor/drafts
and restores the modal's per-document Right/Bottom terminal choice. Inline
views use the regular terminal panel and must not create another renderer or
consume its completion acknowledgement timer. Cancel pending asynchronous opens
when navigation leaves the inline document.

This supersedes the terminal-pill navigation described in
terminal-task-links-open-highlighted-task.md; explicit context-header task
links still reveal the exact task while preserving its saved visibility rules.
