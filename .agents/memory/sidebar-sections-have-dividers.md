# Sidebar sections have horizontal dividers

Top-level sidebar section headings such as Recently updated, Servers, Files,
Pinned, and Meta use a subtle horizontal divider so adjacent trees and lists
remain visually distinct.

Selected workspace folders and worktrees wrap Recently updated and Files in
`.sidebar-worktree-scope`. Apply the same divider and spacing to headings after
the first inside that wrapper; a direct `.sidebar > .sidebar-title` selector
alone misses them. Keep Files free of an extra top divider when it is the only
section in the wrapper.
