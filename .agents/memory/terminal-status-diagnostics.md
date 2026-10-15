# Terminal status diagnostics include browser review

When an agent executed a status command but its dot appears absent, trace the
report through tmux, the API, the browser cache, the rendered dot and its click
acknowledgement before changing agent instructions. Use `lab ui --client ID
terminal-status [NAME]`; it reads the selected view without selecting or
reviewing tabs and compares its report with the current API response.

The compact rail has two independent markers: agent status at upper-right and
Home/folder/worktree location at lower-right (often gray). The existing terminal
refresh runs every eight seconds, so a short working state may fall between
refreshes. A cleared finish retains its message and Reviewed by click in hover,
with the acknowledgement timestamp available through diagnostics. Clicks must
carry the displayed report ID so an old dot cannot acknowledge a later finish.

Verify actual CLI reports through the full browser renderer and native clicks;
model compliance, backend storage, rendering and review are separate checks.
Older browser pages need one reload to load newly added frontend diagnostics.
