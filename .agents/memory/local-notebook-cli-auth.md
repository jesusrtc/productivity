---
title: Local notebook CLI uses a bearer capability
date: 2026-09-03
---

`lab notebook exec` authenticates local `/api/nb` requests with the bearer
token stored at `$LAB_HOME/local-cli-token` (default
`~/.lab/local-cli-token`). The server creates the token with mode `0600` at
startup and accepts it only from loopback and only for `/api/nb` plus child
routes. Local bearer requests still pass through normal workspace resolution;
an unknown explicit workspace must return 404 rather than falling back to the
active root. Do not add header-only cookie bypasses such as
`X-Lab-Local-Automation`, and do not copy browser session cookies into agents.
