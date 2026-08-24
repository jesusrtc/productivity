# Terminal recent activity is selection-local

The terminal rail's recent state means the user selected the tab or just left
it; it does not mean the tmux process merely exists. Record activity both on
attach and detach so a tab that remained selected for hours is still recent
when the user moves away.

Persist recent timestamps as browser-local navigation state, scoped by
workspace plus project/pseudo-project. The highlight window is also
browser-local, defaults to 60 minutes, and is configurable from 1 to 1440
minutes in the terminal header.

Keep the selected tab's existing blue treatment. Only inactive recent tabs get
the green inset marker and dot, so recent and selected states remain visually
distinct.
