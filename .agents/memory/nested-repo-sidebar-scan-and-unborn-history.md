# Nested repository sidebar scans and new-file history

- `/api/project-files` and `/api/project-mtime` share `_PROJECT_SCAN_SKIP_DIRS` and the same bounded-depth logic in `core/routes/diff.py`; keep them synchronized because sidebar contents and refresh detection must describe the same tree.
- The scan depth budget resets at every directory containing a `.git` file or directory, but ordinary source paths must not depend on detecting nested Git metadata. Keep the general cap large enough for `repositories/queries/forge/experimental/cached-queries/cached_queries/tools` while retaining a hard runaway guard.
- Explorer Git history must treat a repository without `HEAD` as valid. Skip `git log` in an unborn repository, then return the `WORKTREE` entry/diff for indexed or untracked files.
- Regression coverage includes deep files under `repositories/queries/forge/experimental/cached-queries/cached_queries/tools` without a `.git` marker, nested-repo untracked files, empty untracked files, and new files before the first commit.
