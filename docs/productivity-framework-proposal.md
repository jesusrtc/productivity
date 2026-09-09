# Lab Vault Framework One-Pager

**Status:** Draft
**Date:** 2026-06-22
**Owner:** Jesus

## TL;DR

Turn Lab into a reusable local framework. The CLI, core server, and UI are installed separately; each user's work lives in one or more independent vault repos created with `lab init`.

`lab start` runs the installed server against one active vault, and the UI has a vault dropdown to switch vaults. Cache, indexes, sessions, server state, and frontend state stay inside the active vault so switching vaults does not leak old data or slow page loads.

Recommended name: **Lab**. It already exists and commands like `lab init`, `lab start`, and `lab workspace new` read naturally.

## Context

The current repo works, but it mixes framework code with user data. The future shape should let anyone install Lab without copying `core`, UI assets, tests, or framework scripts into their own repo.

This must preserve the existing specs:

- `lab` remains the sanctioned write path for workspace/task state.
- `content/` is the vault knowledge base.
- `repositories/` holds external git clones used as references and worktree sources.
- `apps/` holds vault-owned custom CLIs or small apps that workspaces can use.
- The UI stays fast by loading only the active vault.
- The Logs view stays available to users for diagnostics and bug reports.
- The Productivity tab stays visible and always points at the installed Lab framework checkout.

## Proposal

Split Lab into two layers.

**Framework install**

- Owns CLI, core server, UI, framework docs, packaging, and tests.
- Stores only global config and the vault registry under `~/.lab/`.
- Never stores user workspaces, caches, indexes, sessions, or UI state.
- Framework-owned CLI code lives under `core/cli/`; `apps/` is not used for framework internals.

**Vault repo**

- Created with `lab init <path>`.
- Normal user-owned git repo.
- Owns workspaces, docs, skills, scripts, apps, `content/`, `repositories/`, memory, and generated state.
- Its `apps/` folder is user/vault code only: custom CLIs, dashboards, services, or workflows that this vault can use.
- Can be pushed, cloned, backed up, or shared without the framework repo.

Active vault resolution:

1. `LAB_VAULT`
2. nearest parent directory containing `lab.toml`
3. active entry in `~/.lab/vaults.toml`
4. explicit `lab start --vault <path>` if no active vault exists

Keep `LAB_ROOT` as a temporary compatibility alias during migration.

## Vault Registry

Global registry only stores paths and defaults:

```text
~/.lab/
  config.toml
  vaults.toml
```

```toml
active = "personal"

[[vaults]]
id = "personal"
name = "Personal Lab"
path = "/Users/jesus/work/personal-lab"

[[vaults]]
id = "work"
name = "Work Lab"
path = "/Users/jesus/work/work-lab"
```

No cache, index, session, server port file, or UI state should live globally.

## `lab init` Layout

`lab init` creates a complete starter vault:

```text
my-lab/
  README.md
  AGENTS.md
  lab.toml
  .gitignore
  .lab/state/{cache,indexes,sessions}/
  workspaces/example/{workspace.json,tasks.json,docs/,notes/,assets/,scripts/}
  apps/example-cli/{README.md,lab-app.toml,bin/example}
  docs/README.md
  skills/example-skill/SKILL.md
  scripts/hello.py
  repositories/{README.md,.gitignore}
  content/{README.md,updates/,logs/,wikis/}
  .agents/memory/MEMORY.md
```

Required folders: `workspaces/`, `apps/`, `docs/`, `skills/`, `scripts/`, `repositories/`, `content/`, `.agents/memory/`, `.lab/state/`.

Use `scripts/` for simple one-file helpers. Use vault `apps/` for custom CLIs, small services, dashboards, or repeatable workflows that need their own files, dependencies, or commands. Vault apps are user-owned code; the framework discovers and runs them, but does not copy them into the framework install.

`repositories/.gitignore` should ignore cloned repos while keeping `README.md` and `.gitignore` tracked. Each child repo keeps its own `.git`; the vault references those clones but does not absorb them into vault history.

Example `lab.toml`:

```toml
[vault]
name = "My Lab"
version = 1

[paths]
workspaces = "workspaces"
docs = "docs"
skills = "skills"
scripts = "scripts"
apps = "apps"
repositories = "repositories"
content = "content"

[server]
host = "127.0.0.1"
port = 3333

[agents]
default = "codex"
```

## Loading Contract

Lab loads only from the active vault:

- `workspaces/*/workspace.json` and `workspaces/*/tasks.json`
- `workspaces/*/{docs,notes,assets,scripts}/**`
- `docs/**/*.md`
- `skills/*/SKILL.md`
- `scripts/**`
- `apps/*/lab-app.toml` as vault app definitions
- `content/**`
- `.agents/memory/**`
- `repositories/*` as external repo references, not indexed content

Workspace worktrees can be created from `repositories/<repo>` into `workspaces/<id>/worktrees/<repo>-<branch>/`. The source clone stays in `repositories/`; the workspace gets the task-specific working copy.

Vault app commands should be exposed through generic Lab commands, for example `lab app list`, `lab app run <name> -- <args>`, and later `lab app up <name>` for long-running dashboards. Avoid adding domain-specific commands like `lab darwin ...` to core unless the behavior is broadly useful to every vault.

## UI Switching

Add a vault dropdown to the main shell. It lists known vaults from the backend and switches the active vault through an API call.

On switch:

- Stop old vault watchers.
- Clear backend in-memory indexes/caches.
- Clear frontend vault state.
- Load the selected vault from disk.
- Save the active vault in `~/.lab/vaults.toml`.
- Keep the current route if it exists in the new vault; otherwise return to dashboard.

First version optimizes for one active vault. Do not index inactive vaults in the background.

## UI Visibility

Default vault UI should show vault features plus the framework utility tabs: dashboard, workspaces, content/knowledge, code search, notebooks, terminals, logs, and Productivity.

The Logs view should remain available in normal installs because it helps users inspect errors and report bugs.

The Productivity tab points at the framework repo itself and is always visible. Its `__self__` pseudo-workspace must resolve reads, writes, terminal working directories, and task actions against the framework root, not the active vault root.

## Compatibility + Speed Rules

- Preserve existing commands: `lab workspace`, `lab task`, `lab index`, `lab start`, `lab stop`, `lab open`.
- Keep vault app commands behind a generic `lab app` surface so custom CLIs do not bloat the core CLI.
- Keep the old current-repo layout readable for one migration release.
- Do not scan all registered vaults on page load.
- Do not recursively index `repositories/`, `.git`, or inactive vaults by default.
- Serve the cached active-vault index; rebuild in the background where possible.
- Release old watchers, timers, websocket subscriptions, file handles, and caches before loading another vault.
- Keep Logs and Productivity visible in normal installs; Productivity must keep using the framework root even when the active vault changes.

## Test Plan

CLI tests:

- `lab init` creates the full tree, default config, example workspace, example skill, `content/`, and `repositories/`.
- `lab app list/run` discovers vault apps from `apps/*/lab-app.toml` without importing arbitrary app code at startup.
- Discovery order is `LAB_VAULT`, nearest `lab.toml`, then active registry entry.
- `lab vault list/use/current` reads and writes `~/.lab/vaults.toml`.
- `LAB_ROOT` still works during migration.
- `repositories/.gitignore` keeps placeholder files tracked and ignores cloned repos.

Backend/frontend tests:

- APIs expose known vaults, current vault, and switch vault.
- Switching clears stale index data and reloads from the new vault.
- Watchers stop for the old vault and start for the new one.
- Generated state is written under `<vault>/.lab/state/`.
- Existing workspace/task/search/markdown routes still work against the active vault.
- Dropdown renders, switches, clears local state, refetches data, and handles missing vaults cleanly.
- Logs view remains reachable in normal installs.
- Productivity tab is visible by default and loads the framework `__self__` pseudo-workspace without a special startup flag.

Performance/regression tests:

- Keep existing latency budget tests for hot routes.
- Add a test proving page shell load does not scan `repositories/` or inactive vaults.
- Add a vault-switch test proving no stale workspaces/tasks appear after switching.
- Add a resource-discipline test proving repeated switches do not leak watchers, file handles, logging handlers, or async tasks.

Required verification before shipping:

```bash
make test
make test-integration
make test-slow
make perf-prod
```

For a final release candidate, run `make test-all` as well.

## Migration Plan

1. Add vault discovery and registry support.
2. Add `lab init`.
3. Move generated state into `.lab/state/`.
4. Update core to accept an active vault path.
5. Add vault APIs and the UI dropdown.
6. Add required `repositories/` handling.
7. Add vault app discovery under `apps/`.
8. Split the framework repo from one or more vault repos.
9. Migrate current `workspaces/`, `apps/`, `content/`, `repositories/`, and `.agents/memory/` into a vault repo.
10. Package CLI and core together under the `lab` command.

## Open Questions

1. Should skills live only in `skills/`, or also support `.claude/skills/` for compatibility?
2. Should `lab init` always create the example workspace, or support `lab init --no-example`?

## Review Table

| Reviewer | Role | Feedback | Resolved |
|---|---|---|---|
| Jesus | Owner | Pending | No |
