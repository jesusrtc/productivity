# Terminal rail reveals titles without moving icons

The October 9, 2026 correction requires vertical rail expansion to reveal only
terminal titles beside the existing icons. Preserve icon sizes, row heights and
the positions of worktree markers and renewal/review controls across hover.
Activity and recovery controls must not shift compact icons away from center.

Terminal icons sit on the left. Monochrome icons such as GitHub follow the
terminal title's explicit color or its own assigned worktree color. Do not show
task-status dots or yellow activity dots on terminal tabs. Keep status/activity
in accessible labels and preserve explicit green-result review and independent
worktree colors. Task sidebar status controls remain separate.

This supersedes the terminal status-dot presentation in
[Terminal task statuses use small dots](terminal-task-statuses-use-small-dots.md)
and the yellow-dot presentation in
[Terminal output quiet period and review](terminal-output-quiet-period-and-review.md).
