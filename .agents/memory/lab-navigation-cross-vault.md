# Lab navigation is cross-vault

The Lab top bar is a persistent, cross-vault surface. Home is the
permanent framework home. Vault and workspace tabs can remain open together
even when their roots belong to different registered vaults, so navigating
or operating a terminal must pass the owning vault id/path explicitly and
must not call the global vault-switch endpoint.

Vault display name and `#RRGGBB` color live under `display` in that
vault's `vault.json`. Use the color as a subtle tab cue rather than a
space-consuming vault badge. Home Admin owns consolidated servers,
terminals, and logs; Code Search is a scoped inner tab on Home,
vault, and workspace views.
