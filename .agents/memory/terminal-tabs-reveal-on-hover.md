# Terminal tabs reveal on hover

The vertical terminal switcher stays in a 62px icon rail to give the console
more room. Keep session icons, yellow working dots, blinking green completion
dots, scope dots, linked-file markers, active state, and recent activity visible
while collapsed. Hide names and replace Objective names with colored markers.

Hover or keyboard focus reveals the full list; leaving the rail or pressing
Escape collapses it. The expanded list overlays the console, like document
tabs, so xterm's dimensions and text wrapping do not change. Its remembered
width applies only while expanded, with a readable 160px minimum. Preserve
horizontal orientation, terminal selection, menus, and the existing left-side
request tooltips. This supersedes the always-visible resizable vertical rail
in terminal-tabs-resize-labels-automatically.md.
