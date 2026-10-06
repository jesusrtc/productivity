# Objective tasks support Paused and Won’t do

The sidebar status menu supports todo, in_progress, done, paused and wont_do.
Use ⏸ for Paused and 🚫 for Won’t do. Save them in each Objective manifest;
only done sets the completion Boolean. Parent changes other than In progress
also apply to subtasks. All paused children produce Paused; all declined children
produce Won’t do; completed/declined children resolve their parent. Preserve task
Markdown, assets and icon overrides. Paused/declined terminals appear when the
task is selected or Show all terminals is enabled, without changing status.
