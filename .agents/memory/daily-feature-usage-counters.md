# Daily feature usage counters

Home → Logs includes Feature usage: local calendar date plus stable feature
name and count, most used first within each day; All days shows newest days
first. Counts live in vault-local feature-usage.sqlite3 and merge across
registered vaults, independently of diagnostic log rotation or rate limits.
Record successful user actions with window.labFeatureUsage, preserving the
initiating method (+ button, secondary click, drag and drop). Never count
background polling, restored sessions, or a file link's inherited folder as
additional uses. See docs/FEATURE_USAGE.md for coverage and count semantics.
