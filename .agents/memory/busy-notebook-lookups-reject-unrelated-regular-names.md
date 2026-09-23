# Busy notebook lookups can reject unrelated regular names

On POSIX, when the notebook pending registry is small and nonempty, an existing
regular file whose final filename differs from every resolved pending key cannot
be pending. `is_path_pending` checks this with lstat before resolving ancestors.
Keep the filter bounded (currently at 16 active paths); larger registries retain
the original lookup instead of adding an unbounded per-file name search.

Do not apply this shortcut to symlinks, matching names, missing/inaccessible
entries, unusual final path components or non-POSIX platforms. They retain full
resolution under the existing pending lock. Never cache the negative result:
an ordinary entry may become a symlink, an alias may retarget, or run counts may
change without any notebook content edit.

`--pending-notebooks` in the file-scan and navigation performance fixtures uses
owned pending markers only, not actual cell execution. Native navigation checks
both cached pending metadata and actual running dots. Every marker/operation
lease must be cleared, including when the workload fails.
