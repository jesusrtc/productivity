# Assistant tasks are client-global Markdown

The Assistant surface is a permanent admin tab immediately after Home. Its UI
and terminal lifecycle belong to Lab, but its data does not: each client sets
one absolute `LAB_ASSISTANT_HOME` in the Lab checkout's untracked `.env` for a
single task database spanning every registered workspace and project.

The database is Markdown-first (`projects/<id>/project.md` plus one file per
task), keeps exact workspace/project path mappings, and stores only references
to project-owned artifacts. The Lab API/UI is read-only; agents make metadata
changes with `lab assistant` and edit task bodies from the Assistant terminal.
