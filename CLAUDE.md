# Productivity monorepo

You're in a single-user productivity monorepo. Everything lives here.

## How to do anything

Use `lab`. Run `lab --help` for commands. Never hand-edit `project.json`, `tasks.json`, or `.index.json`.

## Where things live

- `content/projects/<id>/` — active projects (one folder each, contains `project.json`, `tasks.json`, `docs/`, `notes/`, `assets/`, and any worktrees). Note: `content/` is its own git repo, untracked from the main monorepo.
- `content/{meetings,wikis,roadmaps,logs,updates}/` — knowledge that isn't project-scoped
- `content/skills/` — shared templates (investigation, one-pager, weekly-update)
- `apps/lab/` — unified CLI (writes)
- `apps/server/` — unified HTTP+WS backend (default port `3333`; override per-run with `make start PORT=NNNN`). The actual port is recorded in `.lab-server.port` on startup. Resolve it from any tool, doc snippet, or curl command via `$(scripts/lab-url.sh)` — do **not** hardcode `localhost:3333`.
- `apps/darwin-backups/`, `apps/trustim-*` — auxiliary CLIs
- `repositories/` — gitignored repo clones (MPs and other repos; added in Plan 4)
- `.claude/agents/` — shared agents (added in later plans)

## Darwin / notebooks

`apps/darwin-runner` and `lab darwin` are **retired** (2026-05-11). For anything that touches Darwin — running Python/PySpark on a Jupyter kernel, Trino/Spark SQL, notebook runs, schedules, pod shell, DataApp, dbt — use the **`darwin-cli` Claude skill**. The on-disk command is `darwin` (LinkedIn's hosted notebook CLI / `go/darwin`). The full command index and examples live in `docs/DARWIN.md`; the authoritative reference is the skill at `~/.claude/skills/darwin-cli/`.

**When the user wants a Darwin run to show up in the lab UI**, do NOT call `darwin code execute` directly. Instead POST to the lab server's notebook executor — it runs the same `darwin code execute` under the hood, appends the cell + outputs to a real `.ipynb` on disk, and the watcher re-broadcasts to every open notebook view:

```bash
curl -s -X POST "$(scripts/lab-url.sh)/api/nb/exec" \
  -H 'Content-Type: application/json' \
  -d '{"path":"content/projects/<id>/notebooks/<name>.ipynb","code":"print(1+1)"}'
```

The kernel session is pinned to the file path (same `path` → same Darwin kernel), so consecutive cells share state automatically. To view the running notebook, open `$(scripts/lab-url.sh)/#/nb?path=<path>`.

## On project work

When you're in `content/projects/<id>/`, read that project's `CLAUDE.md` too. It's auto-generated and contains the project's objective and tool references.

## On sending an update

When the user (typically inside a `content/projects/<id>/`) asks to "send an update", "send a summary", or similar, write a markdown summary of what's been done to `content/updates/<yyyy-mm-dd>-summary.md` using today's date. One flat folder — no `linkedin/`, `personal/`, or other subdirectory split. If a file for today already exists, append a new section to it rather than overwriting. The folder is a user-curated knowledge artifact; we write the file, the user populates and consumes it.

## Archetypes (no types)

Projects are not labeled by archetype. If asked to investigate, draft from `content/skills/investigation/` (once it exists). For a one-pager, use `content/skills/one-pager/`. Pick based on the ask.
