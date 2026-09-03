# Assistant task workspace

Lab's Assistant tab is a client-global view of work that agents should handle.
It is pinned immediately after Home and uses the same persistent terminal
behavior as project tabs. The UI belongs to Lab; the data does not.

## Configure the database

Set one absolute path in the Lab checkout's untracked `.env`:

```dotenv
LAB_ASSISTANT_HOME=/absolute/path/to/assistant
```

Restart Lab after changing it, then initialize the directory:

```bash
lab assistant init
```

`LAB_ASSISTANT_HOME` may also be passed as a process environment override. A
single configured directory is shared by every workspace and project visible
to that Lab client.

## Data layout

The database is Markdown-first and safe to inspect or version separately:

```text
assistant/
  AGENTS.md
  README.md
  projects/
    <assistant-project-id>/
      project.md
      tasks/
        <task-id>.md
      subtasks/
        <subtask-id>.md
      meetings/
        <meeting-id>.md
  .lab/
    project.json
```

`project.md` maps an Assistant grouping to an exact registered Lab workspace
and project path. A task file contains JSON-compatible YAML frontmatter plus an
ordinary Markdown body. Lab reads these files directly; there is no hidden
task database and no copy of a project's artifacts.

Images may be referenced from a task with a relative path or with an absolute
path inside its mapped workspace/project. Lab renders the original file through
an authenticated local endpoint.

## Terminal workflow

The Assistant tab opens a persistent terminal rooted at the configured
database. Agents begin with the generated `AGENTS.md`, which defines the task
format and completion rules. Use the CLI for metadata changes:

```bash
lab assistant path
lab assistant project ls
lab assistant project add launch --name "Launch" --workspace local \
  --path /absolute/path/to/workspace/projects/launch
lab assistant add "Prepare launch note" --project launch --priority P1 --status ready
lab assistant ls --status open
lab assistant set <task-id> status in_progress
lab assistant done <task-id>
lab assistant subtask add "Draft launch email" --parent <task-id> \
  --priority P1 --status in_progress
lab assistant subtask ls --parent <task-id>
lab assistant subtask set <subtask-id> status ready_to_review
lab assistant subtask done <subtask-id>
lab assistant meeting add "Weekly review" --project launch --date 2026-09-03 \
  --attendee "Maya" --attendee "Leo"
lab assistant meeting ls --project launch
```

Edit task and subtask Markdown directly for context, decisions, and outputs.
First-class subtasks are separate documents with their own lifecycle, priority,
owner, due date, and body. New child work should use them; legacy Markdown
checkboxes remain supported for older tasks.
`lab assistant done` refuses to complete the parent while any checkbox or
first-class subtask is incomplete.

Tasks and subtasks may use `waiting_on`, `waiting_since`, `follow_up_at`,
`last_follow_up_at`, and `follow_up_channel` for explicit follow-up routing.
Agent-produced work moves to `ready_to_review`; `reviewer`,
`review_requested_at`, and `executor` record the review handoff.

The Tasks and Meeting notes tabs use compact lists. A single click expands a
short preview; a double click opens the complete Markdown document in a modal.
Every Markdown heading in the modal has buttons for copying that section as
Slack-friendly Markdown or Google Docs-friendly rich text.

The first image referenced by a task is also shown in its expanded preview.
Project-owned images stay in their mapped project and are served only after the
asset path is checked against the Assistant/project/workspace roots.

A task section named `# Generate content` adds a matching action to the expanded
preview. It opens that section in the modal with `Copy content` (formatted,
including embedded images) and `Plain text` actions. Lab never sends the content
or completes the task; those remain explicit manual steps.

## Meeting notes

Meeting notes live below their mapped project in `meetings/`. New notes use a
stable structure: `# Summary`, `# Highlights`, `# Action items`, and `# Notes`.
Checkboxes under Action items are surfaced as individually tracked follow-ups,
including a completed/total count in the list.

## Initial lifecycle

- `inbox`: captured, but not clarified
- `ready`: actionable
- `in_progress`: actively being handled
- `waiting`: awaiting time or an external response
- `blocked`: unable to proceed; the task body should explain why
- `ready_to_review`: agent-produced work is ready for human review
- `done`: complete, with an outcome recorded in `# Result`

Priorities run from `P0` (urgent) through `P3` (someday/maybe). Lab exposes
three comparison views: a flat filter strip, an attention-grouped Focus queue,
and a project ledger. Their shared Focus order is P0, ready to review, in
progress, follow-up due, blocked, inbox, then the remaining work ordered P1
through P3. Waiting tasks use a `Nudge` action to open copy-ready follow-up
content; Lab does not send it or record a message as sent.
