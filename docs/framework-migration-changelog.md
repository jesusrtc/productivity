# Framework Migration Changelog

Generated: 2026-06-23

This document is a migration guide for agents upgrading older Lab checkouts to
the workspace-aware framework layout.

## Current Readiness

Status: ready for a framework commit after review.

Validation run:

```bash
make test
```

Result:

- CLI tests: 161 passed.
- Core/backend tests: 258 passed, 10 slow tests deselected.

Not run:

- `make test-all`
- `make install` from a clean clone
- `make perf-prod`

Important: the current remote `origin/main` only includes commits through
`a3b5be7`. The workspace/framework split is still in the working tree until it
is committed and pushed. A fresh clone from the remote will not include the
pending migration until that happens.

## Fresh Machine Bootstrap

Use this path on a new machine after the framework commit is pushed:

```bash
git clone <framework-repo-url> lab
cd lab
make setup   # only needed if Python 3.11+ is not already available
make install
lab init ~/work/my-lab
cd ~/work/my-lab
lab start
```

Expected behavior:

- `make install` creates framework venvs under `core/cli/.venv` and
  `core/.venv`.
- The `lab`, `core`, `lab-server`, and `gdiff` shims point at this checkout
  from `~/.local/bin`.
- Runtime state is written into the active workspace under `.lab/state/`.
- Global workspace registry is limited to `~/.lab/workspaces.toml`.
- The framework checkout does not need `projects/` or user apps to run.

## Pending Commit: Workspace/Framework Split

This is the uncommitted migration batch currently in the working tree.

Purpose:

- Make this repository the reusable Lab framework.
- Move user work into separate workspace repositories.
- Keep framework code out of root `apps/`.
- Put the installable `lab` CLI under `core/cli/`.
- Keep the backend/UI under `core/`.

Major changes:

- `README.md` now documents the framework install and first-run flow.
- `AGENTS.md` now tells agents that user workspaces are external and selected
  with `lab workspace` or `LAB_WORKSPACE`.
- `Makefile` installs two editable packages: `core/cli` for `lab`, and `core`
  for the backend/UI.
- `core/cli/` is the new installable CLI package.
- `core/src/core/routes/workspace.py` adds workspace API endpoints for the UI.
- `core/src/core/static/js/lab-app.js` adds the workspace dropdown and switch
  behavior.
- Runtime state moves to the active workspace under `.lab/state/`.
- `scripts/lab-url.sh` resolves the running server URL through the active
  workspace state instead of a hardcoded port.
- Root `apps/` framework internals are removed. Root `apps/` is reserved for
  workspace/client apps only.
- Retired or user-owned apps such as old `darwin-backups`, `trustim-ir-cli`,
  and `trustim-investigation` no longer belong in the framework checkout.

Agent migration notes:

- Do not hand-edit `project.json`, `tasks.json`, or `.index.json`.
- Use `lab init`, `lab workspace use`, `lab project`, and `lab task`.
- Keep `.agents/memory/` repo-local, not under `~/.claude`.
- Start project dev servers from the workspace path, not from old clone paths.
- Do not hardcode `localhost:3333`; use `scripts/lab-url.sh` or the CLI.

## Commit History Guide

These are the latest committed framework changes on `origin/main`.

### a3b5be7 - Align agent context across CLIs

Migration impact:

- Agent-facing instructions were unified across supported CLIs.
- Agents should prefer repo-local `AGENTS.md` and `.agents/memory/`.
- When migrating old versions, copy durable memory into the new repo-local
  `.agents/memory/` structure and update `MEMORY.md`.

Agent checks:

- Read `AGENTS.md` first.
- Read `.agents/memory/MEMORY.md` and relevant linked files.
- Do not write memory under `~/.claude`.

### 9ae25b7 - Harden proxy logging and Darwin watcher

Migration impact:

- Proxy errors and Darwin watcher behavior were made safer.
- Darwin runner app paths are legacy. For notebook execution, use the Lab
  notebook executor endpoint so output lands in the UI notebook file.

Agent checks:

- Prefer `POST $(scripts/lab-url.sh)/api/nb/exec` for notebook cells.
- Do not restore retired `apps/darwin-runner`.

### 423e414 - Keep hydration off the first-load path

Migration impact:

- First page load became more latency-sensitive.
- Migration work should not add heavy synchronous work to `/`.

Agent checks:

- Avoid scanning all workspaces or repositories during shell load.
- Keep inactive workspaces out of the default index path.

### 0d9cadf - Keep lab page loads under latency budget

Migration impact:

- Introduced stricter expectations for page-load performance.

Agent checks:

- After large route or UI changes, run `make test`.
- For performance-sensitive changes, also run `make perf-prod` against a
  running server.

### 2c9dfef - Tune production performance verifier

Migration impact:

- Performance verifier behavior was tuned for production-like checks.

Agent checks:

- Use `scripts/lab-url.sh` to locate the active server before performance
  checks.

### 5fd6091 - Add production performance verifier

Migration impact:

- Added the `perf-prod` verification path.

Agent checks:

- Run `make perf-prod` when changing shell load, terminal attach, or proxy
  behavior.

### e5a2de6 through fe83728 - Terminal test hardening

Commits:

- `e5a2de6` Reset terminal attention cache in tests
- `96a67a8` Isolate terminal route tests from real tmux
- `419b7e3` Clarify terminal purge regression assertion
- `113f345` Use pytest readline stub on macOS
- `fe83728` Add terminal auto-spawn regression tests

Migration impact:

- Terminal behavior and tests became less dependent on the user's live tmux
  state.

Agent checks:

- Do not depend on real user tmux sessions in tests.
- Preserve terminal auto-spawn opt-out behavior during UI migrations.

### cba1e37 - Persist terminal auto-spawn preference

Migration impact:

- User preference for terminal auto-spawn is persisted.

Agent checks:

- Preserve workspace/project local UI state during migration.
- Do not wipe `.lab/state/` unless explicitly resetting runtime state.

### 35876c8 - Speed up lab initial page loads

Migration impact:

- Reinforces that first paint must not require heavyweight scans.

Agent checks:

- Keep indexing cached and backgrounded where possible.

### 37f73d8 through 512377d - Shell, logs, and startup changes

Commits:

- `37f73d8` Assert logs terminal priority
- `9a3cef9` Prioritize active terminal pseudo-projects
- `99d7b72` Avoid tmux in logs pseudo-project test
- `fddcdc3` Split lab shell assets
- `31d2737` Improve lab startup latency and proxy safety
- `512377d` Add lab log viewer and lazy heavy assets

Migration impact:

- Logs are now first-class framework UI.
- Heavy frontend assets are lazy-loaded.
- The shell is more modular.

Agent checks:

- Keep Logs visible in normal installs.
- Keep Productivity visible in normal installs and resolve it against the framework root.
- Do not bundle heavy libraries into the initial shell path.

### a9d5220 - Update lab core and agent tooling

Migration impact:

- Broad core and agent tooling update before the framework split.

Agent checks:

- Re-run the full main suite after rebasing older branches across this commit.

### dfe3942 - Move server package to core

Migration impact:

- The backend package moved to `core/`.
- Old references to `apps/backend`, `lab-backend`, or old server package paths
  should be replaced.

Agent checks:

- Use `core/.venv/bin/python -m core` for backend execution.
- Use the `core` script installed by `make install`.

### 3bd94f7 - Code Search tab + configurable lab server port

Migration impact:

- Server port became configurable.
- Code Search became part of the UI.

Agent checks:

- Never hardcode port `3333`.
- Use `scripts/lab-url.sh`, `.lab/state/server.port`, or the CLI.

### cbddcc6 - Per-project reverse proxy for local dev servers

Migration impact:

- Projects can declare proxy entries for local dev servers.

Agent checks:

- Start project servers from the workspace path.
- Verify proxy target ports after moving a workspace.
- If a migrated server still listens from an old path, stop it and restart from
  the new workspace checkout.

## Migrating An Older Flat Checkout

Older versions kept framework code and user work in one checkout. The new
layout separates them.

Recommended agent procedure:

1. Clone or update the framework repo.
2. Run `make install` in the framework repo.
3. Create a new workspace:

   ```bash
   lab init ~/work/my-lab
   ```

4. Copy user-owned folders from the old checkout into the workspace:

   ```bash
   rsync -a old-checkout/projects/ ~/work/my-lab/projects/
   rsync -a old-checkout/content/ ~/work/my-lab/content/
   rsync -a old-checkout/docs/ ~/work/my-lab/docs/
   rsync -a old-checkout/skills/ ~/work/my-lab/skills/
   rsync -a old-checkout/scripts/ ~/work/my-lab/scripts/
   rsync -a old-checkout/repositories/ ~/work/my-lab/repositories/
   rsync -a old-checkout/.agents/memory/ ~/work/my-lab/.agents/memory/
   ```

5. Copy only user-owned apps into workspace `apps/`. Do not copy framework
   internals such as old `apps/lab`. Do not restore retired Darwin runner code.
6. Register and activate the workspace:

   ```bash
   lab workspace use ~/work/my-lab
   lab index rebuild
   lab start
   ```

7. Open the URL printed by `lab start`.
8. Check project proxies and restart any project dev servers from the new
   workspace path.

Do not copy generated runtime state unless intentionally preserving active UI
state:

- `.lab/state/`
- old `.lab-server.pid`
- old `.lab-server.port`
- stale `.devserver.pid`
- stale local logs

## Agent Acceptance Checklist

Before declaring an old checkout migrated:

- `lab workspace current` points at the new workspace.
- `lab project ls` lists expected projects.
- `lab index rebuild` succeeds.
- `lab start` starts the backend and writes `.lab/state/server.port`.
- `scripts/lab-url.sh` returns the running URL.
- UI loads the dashboard for the active workspace.
- Project proxy ports are served by processes whose cwd is inside the new
  workspace.
- No server is still listening from the old checkout path.
- `make test` passes in the framework repo.
- Any remaining old apps are either moved into workspace `apps/` or documented
  as standalone repos.

## Known Portability Notes

- `make install` creates symlinks that point at the local clone path. Run it
  after cloning on every machine.
- Python 3.11+ is required. `make setup` can create a dedicated miniconda env
  if standalone Python is unavailable.
- macOS launchd agent install is machine-local; run `make agent-install` only
  when intentionally enabling always-on startup on that machine.
- Documentation may contain example user paths. Framework runtime code should
  not depend on `/Volumes/SSD`, old clone paths, or a specific workspace name.
