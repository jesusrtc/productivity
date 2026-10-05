# Objective assets use reviewed assignments

The user requires the real workspace Objective tab to put Unassigned assets
first and show whether each has an LLM assignment suggestion. Suggestions target
a task/subtask or an Objective for global assets, carry a reason, and remain
pending until the user accepts them. Reject preserves the current assignment;
identical rejected pairs must not be regenerated. `lab context objectives`
documents the CLI protocol, and the default agent context tells agents to
suggest rather than apply inferred organization.

The Objective tab has live task/asset search, Tasks only / Tasks with assets /
Unassigned / Archive views. Task matches reveal their attachments; asset matches
reveal the owning task. Tasks without optional attachments precede other tasks.
Required specifications are retained.

Starred Objective assets appear above Tasks in the sidebar in every working
view. Unassigned assets and Archive appear only when the Objective overview is
open; opening a task, document or folder hides them. This supersedes the
sidebar asset ordering/visibility in objective-first-navigation-and-overview.md
and live-objectives-use-task-asset-buckets.md. Keep task-list reserved height.
Secondary-click an asset to move it to another task/Objective, Unassigned,
Archive or Trash. Archive is recoverable. Trash requires explicit confirmation,
removes registrations/optional attachments and preserves original files and
running terminals. Mandatory task details cannot be removed.
