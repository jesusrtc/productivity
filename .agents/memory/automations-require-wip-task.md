# Automations require a WIP task

On October 19, 2026 the user required picking one active In progress task for
every automation launch. List workspace WIP tasks with Objective names and
preselect the current WIP task. Without a selection, Launch stays disabled;
without WIP tasks, explain how to make one available. API/CLI previews and
actual launches must reject missing or inactive task ownership, including a task
paused since preview. Never automatically change task status to permit a launch.

The automation's first row owns the chosen task and all subsequent rows inherit
it. When launched from an existing terminal, nest that first row beneath the
existing parent and later steps beneath the first row; the existing parent's
task/main ownership stays intact. Keep the parent's folder for those launches.
Pausing the task hides the complete automation family and parks the active
console immediately. Explicitly selecting the paused task reveals it temporarily.

This supersedes workspace-only/Objective-only automation launches and the old
rule that every step nests directly beneath an existing generic parent.
