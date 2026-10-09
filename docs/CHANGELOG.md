# Lab changelog

User-facing changes to Lab are recorded here alongside updates to the user
guide. This log starts on 2026-10-09; earlier repository history remains in Git.

## 2026-10-09

### Pending tasks and action deadlines

- Objective task navigation includes unfinished tasks and subtasks. Unchecked
  Markdown actions appear in the main dashboard and source documents, excluding
  completed and discarded branches. They no longer add rows or reserved blank
  space to the left Tasks sidebar.
- Action deadlines support `- [ ] [YYYY-MM-DD HH:mm] Action name` in local time.
  The dashboard brings overdue actions and actions due within two days forward.
  Date-only deadlines use the end of that day.
- Clicking an action opens its owning Markdown tab and highlights its exact
  line, including actions inside folded content.
- Completed recurring occurrences stay hidden until their show-again time,
  then reappear with their checklist and subtasks reset for the new occurrence.
