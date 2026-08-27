# Sidebar file history uses one three-pane modal

Recent-file rows expose a visible GitHub-mark action that opens the shared Git
history modal. The worktree/main row exposes the same action for repository-wide
history. Keep changed files on the left, the selected diff in the center, and
revisions on the right; repository history begins with Working tree and the base
branch comparison before commits.

When history starts from a file, each selected revision returns every affected
file and orders the clicked path first so scrolling continues into companion
changes from that commit. For `.ipynb`, keep the first file's semantic cell
revision with Before/After source and output rendering instead of raw JSON.
