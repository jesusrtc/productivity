# Lab

Lab is a local productivity framework: this repo owns the CLI, backend, UI, tests, and packaging. User work lives in separate workspace repos created with `lab init`.

## Install

```bash
make install
```

This installs editable `lab` and `core` shims into `~/.local/bin/`. Keep that directory on your `PATH`.

## First Run

```bash
lab init ~/work/my-lab
cd ~/work/my-lab
lab start
```

`lab init` creates a workspace repo with `projects/`, `content/`, `docs/`, `skills/`, `scripts/`, `apps/`, `repositories/`, `.agents/memory/`, and workspace-local `.lab/state/`.

Use `lab workspace list`, `lab workspace use <path>`, or the UI dropdown to switch workspaces. Only the active workspace is indexed and watched.

The Logs and Productivity tabs are always visible. Logs expose framework runtime
diagnostics; Productivity opens the Lab framework repo itself so framework tasks
and commits stay reachable even while a workspace is active.

## Layout

- `core/cli/` - installable `lab` CLI.
- `core/` - FastAPI/WS backend, UI assets, and framework-owned CLI.
- `apps/` - reserved for workspace/client apps; framework code should not live here.
- `docs/framework-migration-changelog.md` - changelog and migration guide for older Lab versions.
- `docs/productivity-framework-proposal.md` - workspace/framework split proposal and migration plan.
- `docs/superpowers/` - older specs and plans.

Generated runtime state belongs in the active workspace under `.lab/state/`; global config is limited to `~/.lab/workspaces.toml`.
