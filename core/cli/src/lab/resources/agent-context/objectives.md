# Workspace Objectives and assignment suggestions

Objectives own tasks, links, file/document references and worktree memberships
in their workspace's `objectives/<folder>/.objective.json`. Use Lab's locked
store, never hand-edit these manifests or workspace/task metadata.

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
