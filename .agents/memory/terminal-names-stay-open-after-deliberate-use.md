# Terminal names stay open after deliberate use

The user's October 5, 2026 follow-up supersedes the pointer-leave rule in
`terminal-tabs-reveal-on-hover.md`. Reveal vertical terminal names immediately
on hover. A short crossing closes them on leave. Clicking anywhere in the rail
or hovering continuously for 3 seconds keeps the names open while moving to
Files and other views. Only a console pointer click dismisses that deliberate
open state in the mouse flow; preserve Escape for keyboard dismissal.

The delay is configurable in Settings → Global → Terminal appearance and saved
in this browser as `labTermTabHoverPinSeconds`. Default to 3 seconds; allow
0–60 seconds, including fractional values and zero for immediate keep-open.
Do not restart the dwell timer on pointer movement within the expanded rail.
Keep the complete expanded area interactive, including its right edge and
scrollbar. Preserve icon/status visibility, the stable 62px console layout slot,
remembered expanded width, normal horizontal layout, and xterm's text grid.
