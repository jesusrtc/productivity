# Terminal tabs support bulk selection

Cmd-click (Ctrl-click on other keyboards) toggles terminal-tab selection without
attaching a terminal or opening linked files. Start from the mounted tab; keep
selection scoped to the terminal pool and prune sessions that disappear.
Secondary-click inside the selection preserves it; outside selects that tab.
Normal click clears bulk selection and activates the clicked session.

Bulk context actions create or move to one group, ungroup selected members,
associate Home sessions with Home/vault/Logs, unlink files or folders/worktrees,
and close the selected sessions after one count-aware confirmation. Capture
identities and scope before async work. Polls must preserve selection and focus
without replacing or mutating unchanged tab nodes. Browser checks use synthetic
sessions and intercepted mutations, never real running work.
