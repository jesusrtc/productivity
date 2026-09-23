# File scans avoid unnecessary full paths

Building and relativizing a full `Path` for each ordinary file can dominate a
large scan even after switching to `os.scandir`. Reuse one relative directory
prefix and entry names; construct full paths for symlink details, notebooks,
directories, and worktree comparisons. Keep suffix semantics for dotfiles,
uppercase extensions, and Unicode names. Change polling also reuses DirEntry
type/stat data; entries are request-local and must never hide later edits.
