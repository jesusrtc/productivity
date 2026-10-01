# Terminal panel width belongs to each workspace

The user wants the terminal panel's outer width to be independent per workspace,
like Files. Store percentages under labTermPct: with an absolute workspace path
identity, so equally named workspaces in different vaults stay independent.
Folder/worktree and proxy navigation within that workspace use the same width.
Home, Vault, Assistant and Cerebro each retain their own view width.

Restore on workspace/view switches and reload. The old global labTermPct remains
a read-only default for untouched workspaces; new drags never change it. Without
an applicable saved value, clear the preceding view's inline width and use the
stylesheet default. Keep pixel minima, Files widths and terminal tab rail widths
independent. Capture drag ownership so a workspace change before mouse-up cannot
save the outgoing width into the incoming workspace.

Regression coverage: test_frontend_column_resize.py checks migration defaults,
duplicate workspace names, all views, proxy reuse, invalid/denied storage and
interrupted drags; Chrome uses native divider drags and reload across two
workspaces and Assistant.
