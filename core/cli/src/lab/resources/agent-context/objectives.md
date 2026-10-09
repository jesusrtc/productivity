# Workspace Objectives and assignment suggestions

The sidebar and Tasks dashboard list all pending tasks, subtasks and unchecked
action items from each task's own Markdown tab. Completed or discarded tasks
are hidden by default. Repeating branches remain hidden while waiting for their
reactivation time, then return with their existing checkboxes reset.

Action deadlines are optional: `- [ ] [YYYY-MM-DD HH:mm] Action item`. A date
without a time ends that local day; invalid dates remain ordinary text. Undated
actions inherit their task's deadline when available. Overdue items and items
due within two days appear in the dashboard, sorted by deadline. Clicking an
action opens its source tab, reveals folded content and highlights the exact
line without rewriting its Markdown. Preserve existing wording and ownership.

Objectives own tasks, links, file/document references and worktree memberships
in their workspace's `objectives/<folder>/.objective.json`. Use Lab's locked
store, never hand-edit these manifests or workspace/task metadata.

Before working on any Objective or task, read the owning vault's root agent
instructions and the owning workspace's root agent instructions, including
existing AGENTS.md (or agent.md), CLAUDE.md and applicable referenced files.
LAB_VAULT identifies the owning vault; use the Objective/task context or workspace
metadata to resolve its workspace. Read both levels even when the agent starts
in an Objective folder or a linked repository/worktree. Also follow applicable
instructions in those folders. These instructions govern the work without
expanding the Objective/task's authorized scope. See `lab context` for the
shared startup guidance.

Tasks support automatic recurrence through **New task / Edit task** or the
schedule control beside the due date. Configure every X days/weeks/months/years,
a due date, deadline time, time zone and reactivation window. The default window
is one day; daily work can use one hour. Recurrence reopens the same task ID and
its existing subtasks/checklists. Unfinished overdue work keeps its deadline.
Schedule a parent or its subtasks, not both. See `lab context tasks` for the
calendar and reactivation rules shared with document-owned Assistant tasks.

The `task` and `task-update` actions accept `recurrence: null` (Once) or:

```json
{"every":1,"unit":"week","time":"17:00","timezone":"America/Los_Angeles","reactivate_before_minutes":1440}
```

Task payloads expose derived `checklist` (`total`, `done`, `pending`) and
`recurrence_state` (`due_at`, `waiting`, plus queued `next_due`, `next_due_at`,
`reactivate_at`). These are read-only views, not fields to persist. Pending
Markdown action items in the task's own details tab prevent completion, including
parent completion when its own or a child's items remain pending. Checklist
requirements are consequential: agents must use concrete user-defined actions,
preserve their wording, and never invent, tick or remove items to fake progress.

Inspect the current state with `lab objective ls --workspace <workspace-id>`.
It returns the workspace revision, Objective IDs, task/subtask IDs, resources,
shared assets, archived assets and `assignment_suggestions`. Read asset titles,
references and relevant task details before proposing a relationship. Inferred
organization is a proposal for the user to review, not permission to change the
actual assignment.

Write one JSON action to a temporary file, then run:

```bash
lab objective apply --workspace <workspace-id> --expected <revision> --file /tmp/assignment-suggestion.json
```

For an unassigned asset, propose the task that uses it:

```json
{
  "type": "suggest-assignment",
  "objective_id": "source-objective-id",
  "resource_id": "existing-resource-id",
  "destination": {
    "bucket": "task",
    "objective_id": "source-objective-id",
    "task_id": "existing-task-or-subtask-id"
  },
  "reason": "This notebook contains the measurements requested by this task."
}
```

For a global asset, propose an Objective instead. `bucket: "objective"` means
shared across that Objective's tasks; `objective_id` may name another Objective
in the same workspace:

```json
{
  "type": "suggest-assignment",
  "objective_id": "source-objective-id",
  "resource_id": "existing-resource-id",
  "destination": {"bucket": "objective", "objective_id": "destination-objective-id"},
  "reason": "This reference documents the outcome of the destination Objective."
}
```

An asset target is either `resource_id` (optionally with `tab_id` or
`sub_link_id`) or `folder: {"root": "/absolute/registered/worktree", "path": "."}`.
Use exactly the IDs/paths returned by Lab. Do not import a new resource via
`reference`, invent IDs, organize unregistered explorer files, archive task
specifications, or propose archived/removed assets. Across Objectives, move
whole documents or whole registered worktrees; individual owned document
subtabs stay with their owner. Original files and Assistant documents keep their
ownership. A suggestion never launches or relinks terminals.

The action only appends a pending suggestion with a stable ID and reason. It
does not change resource/task/worktree membership, shared stars or Archive.
The user reviews it in the Objective tab with **Accept**, **Reject**, or
**Choose another**. Never call `accept-assignment` on your own proposals. Never
substitute `asset-assign`, `task-asset`, `asset-star`, `asset-bucket`, `asset-trash`
or `remove-resource` for a suggestion unless the user explicitly requested the
actual change. Do not repeat a rejected asset/destination pair; Lab deduplicates
it, including on later runs. Propose a different destination only when the
evidence supports it. If a revision conflict occurs, reread and reconsider.

Suggestions may be `pending`, `rejected`, `accepted` or `superseded`. Pending
suggestions can be accepted only while their asset and destination remain valid.
Acceptance applies the reviewed assignment atomically. Manual classification
can replace an optional task assignment; shared-star controls remain additive.
Archive retains registrations for recovery and hides them from active views and
agent context. Trash removes the registration after user confirmation; source
files and running terminals are preserved.

Assets may have client-defined, named presentation groups with one flat level of
references and a one-second hover reveal. Grouping and order preserve existing
asset URLs, source files, assignments, stars and terminal links. Do not infer or
create groups from matching URLs or document names. Group only when the user
explicitly requests that actual change.

For an explicitly requested group, use `asset-group-create` with `title` and an
existing asset target. Add or move an existing target with `asset-group-member`
and `group_id`; use `group_id: null` to remove it from its group. Rename with
`asset-group-rename` (`group_id`, `title`) or release its references with
`asset-group-ungroup` (`group_id`). `asset-order` takes `item`, `relative` and
`position: "before"` or `"after"`; each entry is an existing asset target or
`{"group_id":"existing-group-id"}`. Reorder only within the same group or the
Objective's outer asset list. Use the revision returned by Lab for every action.
