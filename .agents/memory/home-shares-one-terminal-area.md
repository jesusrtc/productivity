# Home shares one terminal area

Home Overview, Admin, Code Search, and every vault section share the existing
`__self__` terminal scope with no selected-vault override. The selected session,
mounted xterm, WebSocket, groups, New menu settings, and collapsed state stay
consistent across Home section changes. Preserve the live terminal when moving
between Home sections; detach normally when leaving for Assistant or a workspace.
Vault file browsing still uses the selected vault root. All terminal actions,
including polling, New, attaching, and reordering, resolve through
`_termActiveWorkspaceId()` and `_termVaultId()`.

The user explicitly requested closing the old vault-only sessions. Both live
`__vault__` sessions (Local and SSD) were killed and purged on 2026-09-10, with
automatic spawning disabled for those retired scopes. Home's framework terminal
remains admin-only. This supersedes the terminal-scope wording in
`vaults-are-home-sections.md`.
