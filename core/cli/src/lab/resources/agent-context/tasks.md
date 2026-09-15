# Agent-managed tasks in Assistant

Markdown is the source of truth. Agents may create and modify both bodies and
frontmatter directly. CLI commands are optional conveniences for metadata
validation and completion checks. There is no mandatory API write gateway.
Read the database's existing instructions and resolve the exact mapped
workspace before writing. Preserve IDs, relationships, unknown fields and
unrelated content; re-read the latest file before a targeted edit.

In schema 2, tasks and subtasks live in `tasks/<id>.md`, notes in
`notes/<id>.md`, and independent projects in `projects/<id>.md`.
A task has optional `project` and `workspace` IDs, and a null or typed `parent`.
Use JSON-compatible frontmatter with `schema: 2`, `type: "task"`, `id`, `title`,
`status`, `priority`, `created`, and `updated`. Each task requiring its own
outcome or deadline has its own file.

Legacy databases still use `workspaces/<workspace>/tasks/` (or `projects/`).
Run `lab assistant migrate --dry-run` to inspect and `--apply` to migrate with a
backup. Read the database AGENTS.md and manifest before choosing a layout.

## Distinguish three dates

- `created`: capture timestamp; controls date grouping, never changes on edits.
- `scheduled`: the calendar day the user intends to work on it.
- `due`: a real deadline. Do not invent deadlines to make a task appear today.

`defer_until` moves work out of Today/This week until that day, unless it is
already due. All open still contains deferred work. P3 means low priority or
Someday; changing priority does not complete or delete a task. `source: demo`
visibly labels fictional examples. `group` is a searchable workstream label.

Today includes planned or due tasks through today. This week includes planned
or due tasks through Sunday, including overdue tasks. Waiting includes all
waiting work; To review includes reviewable subtasks. Recurring lists tasks
with `recurrence`. Completed includes the last seven days.
Within each view, rows retain creation-date headers, newest day first and
priority/attention ordering within each day. Unknown dates appear last.

```bash
lab assistant add "Prepare review" --workspace demo --status inbox --priority P2
lab assistant set <id> scheduled 2026-09-14
lab assistant set <id> priority P3
lab assistant set <id> defer_until 2026-10-01
lab assistant set <id> status ready_to_review
lab assistant done <id>
```

The agent can freely capture, clarify, reprioritize and defer work as the
user's intent changes. A prepared payment or message is not a completed
payment or sent message. Record outcomes and evidence before marking done.
Client instructions govern specific follow-up owners and execution policy.

## Recurring tasks

Set `recurrence` to `weekly`, `monthly`, or `yearly`. Leave `due: null` until a
real date is known. For a recurring monthly task, `recurrence_anchor` preserves
the initial date's day of month through short months.

```bash
lab assistant set <id> recurrence monthly
lab assistant set <id> due 2026-09-30
lab assistant done <id>
lab assistant repeat <id>
```

`repeat` creates exactly one next-period task and retains the completed file.
Retrying it returns the same next occurrence. `previous_task` and
`recurrence_root` link the history. Short months clamp to their last day and
later months restore the anchor day. It advances one period, even if overdue,
so missed obligations are not silently skipped. New occurrences have fresh
content linked to the previous task; previous results and checked boxes are
not copied as new evidence. No background scheduler runs: agents invoke this
command after completion, or manage equivalent Markdown records themselves.
Subtasks are not cloned automatically.


## Independent Assistant records (schema 2)

After `lab assistant migrate --apply`, records live in flat `tasks/`, `notes/`,
and `projects/` folders. Subtasks share `tasks/`; note types share `notes/`.
`project` and `workspace` are independent optional IDs. `parent` is a typed
object (`{"type":"task","id":"…"}` or `{"type":"note","id":"…"}`).
Use `lab assistant project add <id> --name <name>` to create a project,
`lab assistant note add "Title"` for a note, and `lab assistant verify` to
validate references. Old document paths remain aliases. Read the database's
AGENTS.md for its current contract; do not recreate the legacy folder layout.
