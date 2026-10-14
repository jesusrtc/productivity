# Workspace terminal tabs show the saved name alone

The user explicitly wants tabs such as **ASTA CLI** to show only their saved
name, without a workspace, folder or **main** label beside it. Location markers
keep their existing colors and folder tooltips, but no visible label text.

Named worktree terminals and legacy merged tabs must also retain the saved
name rather than replace it with a worktree label. An unnamed worktree terminal
can use its worktree as the fallback name. Preserve ownership, launch folders,
icons, process identity and the one-active-Objective accordion.

This refines terminal-objective-headers-own-context.md: removing a duplicated
Objective name is insufficient; do not substitute **main** or another context
label next to the user's name.
