# Automation launches wait five seconds

Each workspace terminal automation has a saved launch_delay_seconds setting,
defaulting to 5 seconds for both existing recipes and new ones. The first
terminal starts immediately; wait between newly created terminals, with no wait
after the last. Allow 0 to disable it and 0–300 seconds including fractions.
Show the setting in workspace automation settings and the launch preview.

The server enforces the same delay for UI and CLI launches. Duplicate run UUIDs
remain serialized and adopt live terminals without replaying commands or adding
waits. Do not hold the shared catalog/lifecycle lock during delays. Long CLI
launches need an adequate lab api call --timeout. Commands still run independently;
the delay does not establish readiness or wait for a previous command to exit.
