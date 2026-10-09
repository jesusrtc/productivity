# Lab user guide

Lab is a local workspace for documents, tasks, Objectives, notebooks, terminals
and local applications. This guide explains how users and agents operate Lab.
Vault and workspace instructions own project conventions, content, terminology,
skills and memory policy. Explicit user requests and those instructions take
precedence over framework defaults.

## Tasks, subtasks and action items

Task Markdown checklists represent required work. Checked and pending counts
affect progress, and pending items prevent task completion. Use concrete
actions grounded in the user's actual requirements. Preserve existing wording;
change requirements only when authorized. Do not invent scope, add filler,
delete pending items to claim completion or check an item without verifying
its work.

The Objective Tasks sidebar shows unfinished task and subtask navigation.
Unchecked Markdown actions appear in the main task dashboard and their source
document, without adding rows or blank space to the left sidebar. Completed and
discarded branches are excluded. The dashboard highlights overdue actions and
actions due within the next two days. Write an action's deadline at the beginning of its text:

```markdown
- [ ] [2026-10-12 09:30] Review the alert proposal
- [ ] [2026-10-12] Send the revised document
- [ ] Prepare the agenda
- [x] Review the previous draft
```

Use `YYYY-MM-DD HH:mm` in local time, with a 24-hour clock. Date-only deadlines
use the end of that day. Undated actions remain pending. Click an action to
open its owning Markdown tab, reveal folded content and highlight the exact
action; entering Edit selects its source line.

Recurring tasks keep their ID across occurrences. A completed occurrence
stays hidden until its **show again** time. At that time Lab reopens it and
resets its existing checklist and subtasks, so the new occurrence appears
unchecked. The show-again lead can be configured; the default is one day before
the next deadline. Overdue unfinished occurrences stay obligations rather than
being skipped.

For Assistant tasks and meetings, read `lab context tasks` and
`lab context meetings` before editing their source documents. Only an explicitly
linked content tab owns an Assistant task's checklist; inheriting a navigation
tab does not create checklist requirements for a subtask. Follow client rules
for ownership, research and writing.

When `LAB_DOCUMENT_CONTEXT` is set, read that JSON file for the current absolute
Markdown path and tab ID before working on an Assistant document. This context
does not authorize edits. Preserve sibling documents and tabs. If present,
`LAB_ASSISTANT_HOME` selects the owning Assistant database.
