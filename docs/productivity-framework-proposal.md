# Lab Workspace Framework One-Pager

**Status:** Draft
**Date:** 2026-06-22
**Owner:** Jesus

## TL;DR

Turn Lab into a reusable local framework. The CLI, core server, and UI are installed separately; each user's work lives in one or more independent workspace repos created with `lab init`.

`lab start` runs the installed server against one active workspace, and the UI has a workspace dropdown to switch workspaces. Cache, indexes, sessions, server state, and frontend state stay inside the active workspace so switching workspaces does not leak old data or slow page loads.

Recommended name: **Lab**. It already exists and commands like `lab init`, `lab start`, and `lab project new` read naturally.

## Context

The current repo works, but it mixes framework code with user data. The future shape should let anyone install Lab without copying `core`, UI assets, tests, or framework scripts into their own repo.

This must preserve the existing specs:

- `lab` remains the sanctioned write path for project/task state.
- `content/` is the workspace knowledge base.
- `repositories/` holds external git clones used as references and worktree sources.
- `apps/` holds workspace-owned custom CLIs or small apps that projects can use.
- The UI stays fast by loading only the active workspace.
- The Logs view stays available to users for diagnostics and bug reports.
- The Productivity tab stays visible and always points at the installed Lab framework checkout.

## Proposal

Split Lab into two layers.

**Framework install**

- Owns CLI, core server, UI, framework docs, packaging, and tests.
- Stores only global config and the workspace registry under `~/.lab/`.
- Never stores user projects, caches, indexes, sessions, or UI state.
- Framework-owned CLI code lives under `core/cli/`; `apps/` is not used for framework internals.

**Workspace repo**

- Created with `lab init <path>`.
- Normal user-owned git repo.
- Owns projects, docs, skills, scripts, apps, `content/`, `repositories/`, memory, and generated state.
- Its `apps/` folder is user/workspace code only: custom CLIs, dashboards, services, or workflows that this workspace can use.
- Can be pushed, cloned, backed up, or shared without the framework repo.

Active workspace resolution:

1. `LAB_WORKSPACE`
2. nearest parent directory containing `lab.toml`
3. active entry in `~/.lab/workspaces.toml`
4. explicit `lab start --workspace <path>` if no active workspace exists

Keep `LAB_ROOT` as a temporary compatibility alias during migration.

## Workspace Registry

Global registry only stores paths and defaults:

```text
~/.lab/
  config.toml
  workspaces.toml
```

```toml
active = "personal"

[[workspaces]]
id = "personal"
name = "Personal Lab"
path = "/Users/jesus/work/personal-lab"

[[workspaces]]
id = "work"
name = "Work Lab"
path = "/Users/jesus/work/work-lab"
```

No cache, index, session, server port file, or UI state should live globally.

## `lab init` Layout

`lab init` creates a complete starter workspace:

```text
my-lab/
  README.md
  AGENTS.md
  lab.toml
  .gitignore
  .lab/state/{cache,indexes,sessions}/
  projects/example/{project.json,tasks.json,docs/,notes/,assets/,scripts/}
  apps/example-cli/{README.md,lab-app.toml,bin/example}
  docs/README.md
  skills/example-skill/SKILL.md
  scripts/hello.py
  repositories/{README.md,.gitignore}
  content/{README.md,updates/,logs/,wikis/}
  .agents/memory/MEMORY.md
```

Required folders: `projects/`, `apps/`, `docs/`, `skills/`, `scripts/`, `repositories/`, `content/`, `.agents/memory/`, `.lab/state/`.

Use `scripts/` for simple one-file helpers. Use workspace `apps/` for custom CLIs, small services, dashboards, or repeatable workflows that need their own files, dependencies, or commands. Workspace apps are user-owned code; the framework discovers and runs them, but does not copy them into the framework install.

`repositories/.gitignore` should ignore cloned repos while keeping `README.md` and `.gitignore` tracked. Each child repo keeps its own `.git`; the workspace references those clones but does not absorb them into workspace history.

Example `lab.toml`:

```toml
[workspace]
name = "My Lab"
version = 1

[paths]
projects = "projects"
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

Lab loads only from the active workspace:

- `projects/*/project.json` and `projects/*/tasks.json`
- `projects/*/{docs,notes,assets,scripts}/**`
- `docs/**/*.md`
- `skills/*/SKILL.md`
- `scripts/**`
- `apps/*/lab-app.toml` as workspace app definitions
- `content/**`
- `.agents/memory/**`
- `repositories/*` as external repo references, not indexed content

Project worktrees can be created from `repositories/<repo>` into `projects/<id>/worktrees/<repo>-<branch>/`. The source clone stays in `repositories/`; the project gets the task-specific working copy.

Workspace app commands should be exposed through generic Lab commands, for example `lab app list`, `lab app run <name> -- <args>`, and later `lab app up <name>` for long-running dashboards. Avoid adding domain-specific commands like `lab darwin ...` to core unless the behavior is broadly useful to every workspace.

## UI Switching

Add a workspace dropdown to the main shell. It lists known workspaces from the backend and switches the active workspace through an API call.

On switch:

- Stop old workspace watchers.
- Clear backend in-memory indexes/caches.
- Clear frontend workspace state.
- Load the selected workspace from disk.
- Save the active workspace in `~/.lab/workspaces.toml`.
- Keep the current route if it exists in the new workspace; otherwise return to dashboard.

First version optimizes for one active workspace. Do not index inactive workspaces in the background.

## UI Visibility

Default workspace UI should show workspace features plus the framework utility tabs: dashboard, projects, content/knowledge, code search, notebooks, terminals, logs, and Productivity.

The Logs view should remain available in normal installs because it helps users inspect errors and report bugs.

The Productivity tab points at the framework repo itself and is always visible. Its `__self__` pseudo-project must resolve reads, writes, terminal working directories, and task actions against the framework root, not the active workspace root.

## Compatibility + Speed Rules

- Preserve existing commands: `lab project`, `lab task`, `lab index`, `lab start`, `lab stop`, `lab open`.
- Keep workspace app commands behind a generic `lab app` surface so custom CLIs do not bloat the core CLI.
- Keep the old current-repo layout readable for one migration release.
- Do not scan all registered workspaces on page load.
- Do not recursively index `repositories/`, `.git`, or inactive workspaces by default.
- Serve the cached active-workspace index; rebuild in the background where possible.
- Release old watchers, timers, websocket subscriptions, file handles, and caches before loading another workspace.
- Keep Logs and Productivity visible in normal installs; Productivity must keep using the framework root even when the active workspace changes.

## Test Plan

CLI tests:

- `lab init` creates the full tree, default config, example project, example skill, `content/`, and `repositories/`.
- `lab app list/run` discovers workspace apps from `apps/*/lab-app.toml` without importing arbitrary app code at startup.
- Discovery order is `LAB_WORKSPACE`, nearest `lab.toml`, then active registry entry.
- `lab workspace list/use/current` reads and writes `~/.lab/workspaces.toml`.
- `LAB_ROOT` still works during migration.
- `repositories/.gitignore` keeps placeholder files tracked and ignores cloned repos.

Backend/frontend tests:

- APIs expose known workspaces, current workspace, and switch workspace.
- Switching clears stale index data and reloads from the new workspace.
- Watchers stop for the old workspace and start for the new one.
- Generated state is written under `<workspace>/.lab/state/`.
- Existing project/task/search/markdown routes still work against the active workspace.
- Dropdown renders, switches, clears local state, refetches data, and handles missing workspaces cleanly.
- Logs view remains reachable in normal installs.
- Productivity tab is visible by default and loads the framework `__self__` pseudo-project without a special startup flag.

Performance/regression tests:

- Keep existing latency budget tests for hot routes.
- Add a test proving page shell load does not scan `repositories/` or inactive workspaces.
- Add a workspace-switch test proving no stale projects/tasks appear after switching.
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

1. Add workspace discovery and registry support.
2. Add `lab init`.
3. Move generated state into `.lab/state/`.
4. Update core to accept an active workspace path.
5. Add workspace APIs and the UI dropdown.
6. Add required `repositories/` handling.
7. Add workspace app discovery under `apps/`.
8. Split the framework repo from one or more workspace repos.
9. Migrate current `projects/`, `apps/`, `content/`, `repositories/`, and `.agents/memory/` into a workspace repo.
10. Package CLI and core together under the `lab` command.

## Open Questions

1. Should skills live only in `skills/`, or also support `.claude/skills/` for compatibility?
2. Should `lab init` always create the example project, or support `lab init --no-example`?

## Review Table

| Reviewer | Role | Feedback | Resolved |
|---|---|---|---|
| Jesus | Owner | Pending | No |
