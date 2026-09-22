# Document tasks are independent of content tabs

On September 21, 2026 the user requested a POC with three demo documents in a
separate Assistant POC tab. Tasks should be checkbox records in each document's
JSON metadata, optionally linked to content tabs. Content tabs themselves are
not tasks. The main dashboard lists all tasks and tabs; linked work appears above
the relevant tab's notes. Simple one-line tasks need no tab. The user controls
subtask visibility and can change priority inline.

The user subsequently authorized promoting this to production Documents and
migrating all existing tasks. Preserve the home dashboard and independent stars.
See docs/assistant-document-tasks.md and the assistant-document-tasks migration guide. Remember the last-opened tab for
each document; ordinary document reopening resumes there, while explicit tab
links still open their target. Navigation memory is browser-local per database.

The user clarified that POC documents must open in a modal like the existing
Documents view, with the same left tab rail; do not embed the open document
beside a library on the page. The POC page itself is the document chooser.

Completed task titles stay fully readable without strikethrough or dimming.
Clicking a linked task title (including its subtask count) opens the content tab;
checkboxes change completion and disclosure arrows toggle subtasks.

Tab-associated tasks appear under that tab's group. Nested content tabs with
work form sibling task groups, rather than being duplicated or rolled into
their parent tab's task group. Preserve nesting in the left tab rail. A tab's
own view shows its tasks plus groups for its task-bearing subtabs. Ordinary
tasks/subtasks do not require their own content tabs.

Latest clarification: open each tab with only its direct tasks visible. Hide
ordinary subtasks and descendant-tab work until **Mostrar todo** is clicked;
**Mostrar menos** restores that default. Keep arbitrary-depth tab nesting in
the rail (the demo now includes Tab X → Subtab A → Thread). Show editable task
states Pendiente / En progreso (WIP) / Bloqueada / Completada, visible WIP badges,
and a scope-respecting WIP filter. Store statuses in each document's task JSON.

Task titles are the navigation link. Do not add a separate tab-name link or
arrow button beside each task; the user removed those duplicate controls.

The POC document chooser should resemble the ordinary Documents list: full-width
rows with icon, title and summary, plus visible pending task counts and WIP/
blocked indicators. Distinguish notes without tasks from completed work. Keep
modal opening and last-tab memory when clicking a row.

The user prefers thin, Jira-like document rows instead of tall cards. Use a
single desktop line with title and muted summary inline, smaller icons/text,
and compact task-status badges; apply the same density to Documents and POC.

Production refactor: preserve creating/editing content tabs and arbitrary nested
subtabs, the note editor, series navigation and existing task metadata/recurrence.
Task creation/editing is independent of tab creation. Remove the separate POC UI.
