# Retain unchanged rows during background sidebar refreshes

Background workspace refreshes (`preserveScroll`) still fetch current data and
generate current markup, including selection, folder state, filters, and notebook
activity. When that markup, scope, and mounted root identity match, keep the live
rows. Replacing thousands of unchanged rows delays terminal input and loses focus.

Explicit navigation still clones pristine templates. Changed markup or another
view replacing the sidebar invalidates the live reuse. Git and instruction-file
refreshes continue even when the file tree is unchanged. Retained rows can skip
reapplying fresh cached Git styling; stale/missing status must still fetch and
apply, with the existing workspace/worktree response guard. Do not cache live nodes
across workspace switches or increase the existing template memory bounds.

The 5,000-file typing fixture still exposes startup layout and large render-task
misses; this optimization alone does not establish the 50 ms typing target.
