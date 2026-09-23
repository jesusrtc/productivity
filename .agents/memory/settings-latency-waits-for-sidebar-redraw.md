# Measure settings saves through their visible result

The `--settings` navigation probe keeps Alpha active while opening Global settings,
editing Beta's model, then changing Alpha's Recently updated visibility. Validate
the captured workspace on every step and both metadata files afterward. Sidebar
preferences live in browser storage; verify persistence plus complete row removal
or restoration. The Saved message alone can precede the asynchronous redraw.

Measured actions use timestamped native clicks. Text is entered through CDP; select
values are prepared before timing the Save click because native macOS select popups
did not commit page-CDP arrow events. Do not report that setup as dropdown latency.
Keep all failures and label CPU/full-trace runs separately from untraced checks.
The report's timeOrigin aligns native sourceEpoch values with navigation trace time.
