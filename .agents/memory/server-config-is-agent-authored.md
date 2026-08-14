# Server config is agent-authored

When a project needs Lab server tabs, create `servers.json` as an explicit
template and let an agent fill in its server entries. Do not inspect or infer
configuration from a project's Makefile. Make targets may still be referenced
as explicit `start_command` and `stop_command` values inside `servers.json`.
