# Nested repository sidebar scans and new-file history

- `/api/project-files` and `/api/project-mtime` share `_PROJECT_SCAN_SKIP_DIRS` and the same bounded-depth logic in `core/routes/diff.py`; keep them synchronized because sidebar contents and refresh detection must describe the same tree.
- The scan depth budget resets at every directory containing a `.git` file or directory. This lets checkouts under `repositories/` expose their normal source tree without removing the project-root runaway-scan guard.
- Explorer Git history must treat a repository without `HEAD` as valid. Skip `git log` in an unborn repository, then return the `WORKTREE` entry/diff for indexed or untracked files.
- Regression coverage includes deep files under `repositories/queries/forge/experimental/cached-queries/cached_queries/tools`, nested-repo untracked files, empty untracked files, and new files before the first commit.
