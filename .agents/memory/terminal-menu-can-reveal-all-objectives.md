# Terminal menu reveals all sessions

Provide Show all terminals in the terminal menu and fixed-main context menu.
It uses the saved WIP filter setting: turning it off reveals all statuses and
unfolds every Objective with sessions, including parked Objectives. Toggling
again returns to one expanded Objective and its saved task filter (WIP + selected
task unless Show all is enabled on that Objective). The workspace main and active
Objective main stay visible in both modes; inactive Objective mains stay hidden.
Expansion does not make other Objectives current; only the selected Objective
keeps active colors. Existing independent children
still use their hover/focus hierarchy.
