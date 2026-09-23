# Shared project and worktree folders

Lab discovers direct project folders under `~/src` by default. The shared
worktrees root defaults to `~/src/.worktrees`, with one project directory and
then one branch directory, e.g. `~/src/.worktrees/lab/new-feature-branch`.
Both roots are editable in Global → Projects and worktrees, using the validated
client-wide settings writer. Custom project paths and per-project worktree
parents are remembered in the same catalog. Workspace → File sidebar → Add
project offers a filtered list and a custom-folder option; workspace shortcuts
remain browser-local. Empty worktree fields inherit the shared default, while
existing explicit workspace paths keep precedence. Settings never move files.

New catalog projects use this layout in `lab workspace add`; `--project-path`
selects a custom source and `--worktree-path` overrides one destination.
Legacy vault repositories retain their existing layout. Scans support ordinary
non-Git projects and absent worktree folders, and settings previews are read-only
admin operations. Preserve vault-user access boundaries for external projects.
