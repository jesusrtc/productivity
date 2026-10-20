# Progress reminders support snooze only

On October 20, 2026 the user requested only Snooze 30 min, removing Dismiss.
This supersedes permanent dismissal in floating-alerts-top-progress-mutes.md.
Remove its UI and programmatic action, and ignore legacy saved dismissals so
reminders cannot remain hidden indefinitely. Retain finite 30-minute snoozes,
repeat snoozing when reminders return, history, exact-alert/incarnation safety,
browser reload/window persistence, and the actual working status.
