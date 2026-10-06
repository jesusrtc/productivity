# Terminal recency bar is opt-in

The October 6, 2026 request disables the terminal recency bar by default. Show
it only when the user explicitly enables Show recency bar on terminal tabs in
Settings → Global → Terminal tabs. Persist that choice in the browser under
`labTermRecentEnabled`; saved window, color and activity from the old default
must not count as opting in. Keep the window/color preferences and navigation
timestamps so the existing recency behavior remains available when enabled.

The earlier 60-minute default in `terminal-recent-tab-activity.md` now applies
only to the window after opting in. Completion and working indicators remain
independent of the recency setting.
