# Reuse equal sidebar sections when file data changes

For background workspace refreshes, compare previous and next pristine templates
and retain equal live sections. Reconcile known folder/recent/worktree containers
by stable IDs, file paths/roots, and folder paths/scopes. Update changed container
attributes, clone changed rows, and remove obsolete ones. Validate live child
identity before using its old template; a different writer can invalidate it.
Navigation still clones pristine templates. Never put decorated live nodes into
the template cache. Scope and generation guards still apply before rendering.

Use `moveBefore` when available to retain focus during reordering; otherwise
restore only the same surviving focused element after the move. Keep native file
search, every row, history/file/modal handlers, and drag/context metadata.

Check measured template retention rather than assuming it: the mixed 5,000-file
fixture originally had 60,189 live elements, just beyond the 60,000-element cache
limit, so incremental reuse never ran. Moving history graphics to a button
pseudo-element removed 5,004 wrappers in that fixture and brought the retained
template to 55,185 elements. The four-scope/60,000-element limits remain unchanged.
The subsequent [fragment reuse](sidebar-template-fragments-reuse-pristine-folders.md)
change avoids reparsing unchanged folders while assembling the next template.
HTML generation and cloning still take work; do not report this as a complete
50 ms solution.
