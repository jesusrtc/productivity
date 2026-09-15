# Command+K keeps the active file scope

Command+K (and Ctrl+K) finds file names and paths within the selected sidebar
folder and Git worktree. Capture the workspace, repository, folder, and worktree
when the picker opens. Fetch files from that exact root and pass the same root
when opening a result. Do not navigate to another workspace or synchronize a
linked terminal's scope. Discard stale results when the context changes, and
never fall back to the main checkout if the selected worktree is unavailable.

Reuse Recently updated's accepted file-type list to order results: accepted
formats first, then all other formats, with modification time descending in
each group. Apply the same order before and after typing a query.
