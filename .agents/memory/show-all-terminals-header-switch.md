# Show all terminals is a header switch

On October 19, 2026 the user requested a Show all on/off toggle at the top of
the terminal panel, beside Terminal, replacing the Objective's All shown button.
Keep it visible while terminal names are folded and expose an accessible switch
with native keyboard activation. On reveals all task statuses; off restores
In progress and explicitly selected paused tasks plus generic terminals.

Use the existing saved browser WIP setting as the single source of truth and
keep Terminal settings synchronized. Remove per-Objective controls and ignore
their legacy terminalAll overrides, so the header cannot say off while one
Objective still shows everything. Preserve one expanded Objective, task focus,
active sessions and notification-specific temporary reveals.

This supersedes `objective-header-can-reveal-all-its-terminals.md` and the New
menu placement described in `terminal-menu-can-reveal-all-objectives.md`.
