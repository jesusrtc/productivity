# Terminal clicks select tasks and open their linked assets

Terminal-tab clicks and notification clicks must select the owning Objective
and task/subtask, then open the exact linked notebook, file, document subtab or
URL sublink while keeping Task assets accessible. A terminal without a separate
asset opens its task details. Keep the exact selected session, including
secondary terminals and children that inherit a task; never substitute its
primary or launch another session.

An explicit/inherited task binding wins. Otherwise resolve a unique existing
assignment of the linked asset for navigation only, without rewriting terminal
ownership, cwd or visibility. Exact subtab assignments beat whole-document
assignments. For shared assets, keep an already selected matching task or leave
task selection empty rather than guessing. A linked folder must not call
selectScope while task navigation is active: that enters worktree browsing and
clears task focus. This supersedes the earlier notification-only preference
that deliberately skipped asset navigation.

Browser regression coverage must click the real terminal rail listener and
notification card with the real Objectives module. Cover asset-only notebook
links, equivalent absolute file paths, exact subtabs/sublinks, inherited child
sessions, legacy links, shared assets and preserved sidebar Task assets.
