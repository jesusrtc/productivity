# Assistant tasks are client-global Markdown

The Assistant surface is a permanent admin tab immediately after Home. Its UI
and terminal lifecycle belong to Lab, but its data does not: each client sets
one absolute `LAB_ASSISTANT_HOME` in the Lab checkout's untracked `.env` for a
single task database spanning every registered vault and workspace.

Admins configure that folder from Home → Admin → Assistant. Saving initializes
the Markdown database, persists `LAB_ASSISTANT_HOME`, and switches the running
server immediately. The Assistant tab is workspace-shaped: Overview plus Tasks
and Meeting notes, the standard Files/Recently updated sidebar rooted at that
folder, and the existing Assistant terminal.

The database is Markdown-first (`workspaces/<id>/workspace.md` plus one file per
task), keeps exact vault/workspace path mappings, and stores only references
to workspace-owned artifacts. Agents make task metadata changes with
`lab assistant` and edit task bodies from the Assistant terminal; the only UI
mutation specific to Assistant is its admin-owned folder configuration
(ordinary file explorer actions are shared with workspace views).
