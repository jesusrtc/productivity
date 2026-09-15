# Assistant tasks are independent of project/workspace storage

On September 15, 2026 the user requested a data-model redesign:

- Each task may have one project and one symbolic workspace association. A
  project may span workspaces, and a workspace may contain multiple projects.
- The workspace is a convenient view of associated work, not a required place
  to execute the task or a physical owner of its file.
- Tasks and notes should live in their own top-level folders, with optional
  projects and robust references. The task document rail should become nested
  tabs/subtabs like Google Docs, supporting subtasks or threads.

The concrete proposed schema, identity rules, tab interactions, workspace view,
and migration/recovery plan are in `docs/assistant-independent-records.md`.
This is a design proposal, not an implemented storage migration. The existing
client database and legacy links have not been moved. Before implementation,
check whether the user has selected subtasks plus notes/threads or only subtasks.
