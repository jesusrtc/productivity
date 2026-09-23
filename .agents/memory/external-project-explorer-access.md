# External projects share explorer access checks

The configured project and worktree roots must be accepted by `_entry_root`
as well as Git status and worktree discovery. File history, revision diffs,
patch previews, agent-context inspection, and create/rename/delete actions all
use this explorer gate. Otherwise external projects browse successfully but
History reports “Path is outside the vault”.

Use the existing approved-location check only for admins outside their scoped
vault. Keep ordinary vault users confined to their authorized root, reject
unconfigured external paths, and retain relative-path and symlink-parent checks.
Regression tests use real external Git projects and worktrees for both shared
and custom locations, with committed and working-tree history.
