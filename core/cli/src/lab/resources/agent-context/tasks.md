# Agent-managed tasks in Assistant

Markdown is the source of truth. Agents may create and modify both bodies and
frontmatter directly. CLI commands are optional conveniences for metadata
validation and completion checks. There is no mandatory API write gateway.
Read the database's existing instructions and resolve the exact mapped
workspace before writing. Preserve IDs, relationships, unknown fields and
unrelated content; re-read the latest file before a targeted edit.

## One task/note file, including all subtabs

The current format is `embedded-subtabs-v1` within schema 2. An independent task
lives in `tasks/<id>.md`, a note in `notes/<id>.md`, and all its nested subtabs
live inside that same file. Metadata for subtabs goes in the frontmatter `tabs`
array; stable body markers delimit their Markdown. Independent projects use
`projects/<id>.md`. Subtabs inherit the root's project/workspace references.
Read `lab migrations assistant-subtabs` for the exact format and examples.

Use `lab assistant subtab add "Title" --parent <id> --parent-type task|note`,
then `lab assistant subtab set <id> status in_progress` (or not_started, done,
skipped). `owner` is POC; `tldr` is the one-line description; due and priority
are per-subtab fields. Subtask and thread are one user-facing concept: subtab.
Older CLI aliases and IDs remain compatible; do not duplicate child documents.

An Index tab appears only when there are subtabs. It shows their clickable tree,
description, status, due, priority and POC. Overall status derives recursively:
none started → Not started; some started, completed or skipped → In progress;
all completed/skipped → Completed. Skipped completes a branch without deleting
its contents. Overall Cancelled is manual. A single-tab task has manual status.

Markdown remains authoritative; `.assistant/index.json` is generated and
rebuildable. Lab updates it after writes and detects direct Markdown changes on
reads/refresh. Run `lab assistant verify` after edits. Re-read the containing
file and preserve siblings when several agents work on the same task.

Read the manifest before changing layout. Separate-record schema 2 converts
with `lab assistant migrate --embedded --dry-run` / `--apply`, with backup and
ID/body/alias preservation. Legacy workspace-folder databases first use the
existing `lab assistant migrate --dry-run` / `--apply` conversion. Reading
`lab migrations` or agent context never modifies data.

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
