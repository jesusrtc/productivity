# Watched terminal notifications stay until corner close

On October 21, 2026 the user requested terminal-tab secondary-click Watch/fix
controls: remind in 10/30 minutes, 1/2/6 hours, tomorrow at local 9 AM, or pin
immediately. The latest notification must remain visible until the user closes
it with a corner ×, including after navigation, reviewing green or new working
reports. New alerts update its contents. Unreported shells get a yellow manual
check, without invented agent status.

Persist the watch and deadline with the exact running session across clients
and reloads. A deadline while closed/asleep appears on next open/wake. Close
only that exact watch/report, retain history and agent status, and allow future
alerts. Keep regular progress/automation reminders snooze-only unless the user
explicitly watches that terminal. Provide cancellation and the same operation
through the discoverable Lab API/CLI. Never transfer watches to recreated tabs.
