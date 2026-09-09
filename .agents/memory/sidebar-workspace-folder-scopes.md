# Sidebar workspace folders scope the complete file view

File-view settings can define browser-local workspace folders with a label,
color, and optional per-workspace worktree parent. Every sidebar shows Root plus
one colored button per configured folder and remembers the selected folder for
that sidebar's base root. Resolve the selected workspace folder first, then its
selected Git worktree; Recently updated and Files must always use that same
final root. Relative folder inputs are resolved from the current Root.
