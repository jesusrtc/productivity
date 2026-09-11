# Home terminal section associations

Home, vault sections, and Logs share the `__self__` terminal pool. Logs reserves
the visible terminal width instead of hiding or covering it; manual collapse
still works. This supersedes the hidden-terminal layout in
`logs-are-a-home-section.md` and the single-selection behavior in
`home-shares-one-terminal-area.md`.

Sessions have browser-local Home, `vault:<id>`, or Logs associations, stored by
logical name in `labTermHomeAssociations` with their most recent selection time.
Vault badges follow catalog colors; Logs is red. New and attached sessions
capture their originating section before asynchronous work, and the tab context
menu can reassign them without moving the process, cwd, file links, or custom
groups. Existing folder-linked sessions infer their vault; other sessions default
to Home. Clicking a Home section restores its most recently used associated
session when available. All sessions remain accessible in the shared rail.
