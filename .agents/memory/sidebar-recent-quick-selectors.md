# Recent files use one quick-selector scope

The sidebar exposes two quick-selector rows below Overview: 15m, 1h, 2h, 6h,
and 24h by file mtime; then Uncommitted, vs origin/main, and Last 2 commits by
Git. Exactly one scope is active. Clicking the active button again selects
None and hides Recently updated. The maximum time window is 24 hours; migrate
older 3-day, 7-day, and 30-day browser values to 24 hours. Keep the full File
view settings behind the cog beside Overview.
