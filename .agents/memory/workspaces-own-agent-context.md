# Workspaces own their agent instructions

The user wants workspace autonomy: no Lab-generated AGENTS.md/CLAUDE.md,
instruction/skill symlinks, or imposed workspace memory configuration.
Framework capabilities are shipped as package resources and injected through
`lab agents run` at terminal launch; `lab context [markdown|notebooks|servers]`
reads the guide anywhere. Workspace-owned instructions take precedence over
the guide's defaults. Preserve the provider's existing instructions/config.

`lab agents sync` and its API are now read-only. `lab agents detach` removes
recognized old links after recording original targets in client state, leaving
all real files and custom links intact. Do not reintroduce automatic linking,
instruction seeding, or shared skills under workspaces. This supersedes the old
cross-agent symlink/auto-memory sync workflow; the framework repo's own memory
policy still applies to framework work.
