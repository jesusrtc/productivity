# First column mirrors the terminal rail

The user's October 8, 2026 request adds deliberate-open behavior to the first
column. On desktop workspace, Home, vault and Assistant views, retain a 62px
compact sidebar. Hover reveals the complete sidebar over the main area; a
short crossing closes on leave. Selecting a sidebar row or dwelling for the
terminal hover keep-open delay keeps it expanded until a click in the main
work area or terminal console. Escape also dismisses it. Preserve navigation,
drafts, status/icons, scroll and per-view expanded widths; do not resize the
terminal grid when the sidebar opens or closes.

Reuse `labTermTabHoverPinSeconds` (default 3 seconds, 0–60) in Settings →
Global → Terminal appearance for both rails. An ordinary main-area click
changes only transient drawer state, never the saved Files visibility. Legacy
hidden preferences become compact rails on desktop; mobile keeps the existing
explicit Files toggle. Navigation from outside the sidebar resets deliberate
open state. Include the new sidebar script in the shell asset fingerprint and
restart the backend when changing its template include.
