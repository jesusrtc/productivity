# Assistant task database

Lab's Assistant tab is a client-global view of work that agents should handle.
It is pinned immediately after Home and uses the same persistent terminal
behavior as workspace tabs. The UI belongs to Lab; the data does not.

## Configure the database

Open **Home → Admin → Assistant**, enter an absolute folder path, and choose
**Use folder**. Lab creates the folder when needed, initializes its Markdown
contract, saves the selection in the checkout's untracked `.env`, and starts
using it immediately.

The equivalent configuration is:

```dotenv
LAB_ASSISTANT_HOME=/absolute/path/to/assistant
```

When configuring by hand, restart Lab and initialize the directory:

```bash
lab assistant init
```

`LAB_ASSISTANT_HOME` may also be passed as a process environment override. A
single configured directory is shared by every vault and workspace visible
to that Lab client.

## Data layout

The database is Markdown-first and safe to inspect or version separately:

```text
assistant/
  AGENTS.md
  README.md
  workspaces/
    <assistant-workspace-id>/
      workspace.md
      tasks/
        <task-id>.md
      subtasks/
        <subtask-id>.md
      meetings/
        <meeting-id>.md
        <meeting-id>/raw.txt
        <meeting-id>/questions/<content-id>.md
        <meeting-id>/documents/<content-id>.md
      meeting-series/
        <series-id>.md
  .lab/
    workspace.json
```

`workspace.md` maps an Assistant grouping to an exact registered Lab vault
and workspace path. A task file contains JSON-compatible YAML frontmatter plus an
ordinary Markdown body. Lab reads these files directly; there is no hidden
task database and no copy of a workspace's artifacts.

Images may be referenced from a task with a relative path or with an absolute
path inside its mapped vault/workspace. Lab renders the original file through
an authenticated local endpoint.

## Terminal workflow

The Assistant tab opens a persistent terminal rooted at the configured
database. Agents begin with the generated `AGENTS.md`, which defines the task
format and completion rules. Agents may create and edit Markdown directly,
including frontmatter. The CLI provides convenient IDs and validation:

```bash
lab assistant path
lab assistant workspace ls
lab assistant workspace add launch --name "Launch" --vault local \
  --path /absolute/path/to/vault/workspaces/launch
lab assistant add "Prepare launch note" --workspace launch --priority P1 --status ready
lab assistant ls --status open
lab assistant set <task-id> status in_progress
lab assistant done <task-id>
lab assistant subtask add "Draft launch email" --parent <task-id> \
  --priority P1 --status in_progress
lab assistant subtask ls --parent <task-id>
lab assistant subtask set <subtask-id> status ready_to_review
lab assistant subtask done <subtask-id>
lab assistant meeting add "Weekly review" --workspace launch --date 2026-09-03 \
  --attendee "Maya" --attendee "Leo"
lab assistant meeting ls --workspace launch
```

Edit task and subtask Markdown directly for context, decisions, and outputs.
First-class subtasks are separate documents with their own lifecycle, priority,
owner, due date, and body. New child work should use them; legacy Markdown
checkboxes remain supported for older tasks.
`lab assistant done` refuses to complete the parent while any checkbox or
first-class subtask is incomplete.

Tasks may set `group` to an task group or workstream within their mapped
Lab workspace, and `tldr` to the one-sentence summary shown in the list and modal.
Use `lab assistant set <task-id> group "Release operations"` and the same form
for `tldr`, or edit their JSON-compatible frontmatter values directly.

Tasks and subtasks may use `waiting_on`, `waiting_since`, `follow_up_at`,
`last_follow_up_at`, and `follow_up_channel` for explicit follow-up routing.
Agent-produced work moves to `ready_to_review`; `reviewer`,
`review_requested_at`, and `executor` record the review handoff.

The Tasks tab selects one mapped workspace and lists tasks directly under
`yyyy-mm-dd` creation-date headers, newest day first. Workstream labels remain
visible and searchable. Priority/attention ordering is retained within each day;
unknown dates appear last. Clicking a row opens the existing compact modal with
main task and first-class subtasks in the rail, and section copy controls.

Views include All open, Today, This week, Inbox, To review, Waiting, Recurring,
Someday and Completed. `scheduled` is the planned working day, `due` is the real
deadline, and `created` is the capture date used for grouping. `defer_until`
postpones visibility in Today/This week unless a task is already due. P3 tasks
also appear in Someday. `source: demo` labels fictional examples visibly.

`recurrence` can be weekly, monthly or yearly. After a task is done,
`lab assistant repeat <id>` creates the next occurrence once; retries return the
same file. `recurrence_anchor` retains the intended day across short months.
Unknown due dates must be confirmed first. Each completed period remains as
history. This is explicitly agent-managed; no background scheduler runs.
Read `lab context tasks` for the complete date and recurrence contract.

The Assistant tab opens on **Overview**. Like a normal workspace, it has the
standard **Recently updated** and **Files** sidebar rooted at the selected
Assistant folder. Overview summarizes open work, mapped workspaces, and recently
changed files; **Tasks** and **Meeting notes** remain dedicated subtabs. Files
open in Lab's normal Markdown/code/notebook viewer while the Assistant terminal
stays associated with the global Assistant workspace.

The first image referenced by a task is also shown in its expanded preview.
Workspace-owned images stay in their mapped workspace and are served only after the
asset path is checked against the Assistant/workspace/vault roots.

A task section named `# Generate content` adds a matching action to the expanded
preview. It opens that section in the modal with `Copy content` (formatted,
including embedded images) and `Plain text` actions. Lab never sends the content
or completes the task; those remain explicit manual steps.

## Meeting notes

Meetings start across all workspaces without inherited task search filters.
Lists and histories have newest-first date headers; unknown dates appear last.
Rows show the series name, or a standalone meeting title. Open a row to read
Summary, Highlights and Action items. Only checkboxes in Action items count as
follow-ups. Legacy Notes and other sections remain separate Supporting notes.

Explicit workspace-local series live in `meeting-series/`. The Series view
shows descriptions and dated occurrences. Related questions and documents
live in companion folders; each appears separately in the document rail.
Optional original UTF-8 snapshots in `raw.txt` are create-only and byte-preserved.
They render as plain text with a raw-copy action. Missing originals are not
reconstructed from supporting notes. Linked external documents are references.

```bash
lab assistant meeting series add weekly --workspace launch --title "Weekly review"
lab assistant meeting add "Review" --workspace launch --series weekly --date 2026-09-14 --raw-file notes.txt
lab assistant meeting add "Unknown date" --workspace launch --undated
lab assistant meeting content add "Why?" --meeting <id> --kind question
lab assistant meeting content add "Brief" --meeting <id> --kind document --file brief.md
lab context meetings
```

The packaged meeting context documents storage, commands and compatibility.
Client instructions continue to own task ownership, terminology, research and
writing requirements. Framework updates do not rewrite them. Files are the
source of truth; the API derives its views from those same files on refresh.

## Initial lifecycle

- `inbox`: captured, but not clarified
- `ready`: actionable
- `in_progress`: actively being handled
- `waiting`: awaiting time or an external response
- `blocked`: unable to proceed; the task body should explain why
- `ready_to_review`: agent-produced work is ready for human review
- `done`: complete, with an outcome recorded in `# Result`

Priorities run from `P0` (urgent) through `P3` (someday/maybe). Each Lab-workspace
selector shows the unique number of open tasks needing attention because they
are P0, in progress, ready to review (directly or through a subtask), or due
within three calendar days. This due-soon window is provisional. Secondary
status and priority filters apply only inside the selected Lab workspace. Waiting
tasks use a `Nudge` action to open copy-ready follow-up content; Lab does not
send it or record a message as sent.

## Editing document properties

Task and note documents keep their content in the main pane. The compact
header contains the title and editable properties: task status, priority, Due
with a calendar, and Repeats; meeting notes have Date and Series. The `···`
menu holds additional properties and workspace context. Changes save on
selection or leaving a field, with a visible save/error message.

`PATCH /api/assistant/metadata` updates one allowlisted field on an existing
document using its relative path and expected previous value. It preserves
task completion checks and rejects stale values. Recurrence remains explicit:
changing Repeats does not create or schedule the next occurrence.
