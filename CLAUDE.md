# Productivity monorepo

You're in a single-user productivity monorepo. Everything lives here.

## How to do anything

Use `lab`. Run `lab --help` for commands. Never hand-edit `project.json`, `tasks.json`, or `.index.json`.

## Where things live

- `content/projects/<id>/` — active projects (one folder each, contains `project.json`, `tasks.json`, `docs/`, `notes/`, `assets/`, and any worktrees). Note: `content/` is its own git repo, untracked from the main monorepo.
- `content/{meetings,wikis,roadmaps,logs}/` — knowledge that isn't project-scoped
- `content/skills/` — shared templates (investigation, one-pager, weekly-update)
- `apps/lab/` — unified CLI (writes)
- `apps/server/` — unified HTTP+WS backend on :3333 (reads/writes + gdiff project view)
- `apps/darwin-*`, `apps/trustim-*` — auxiliary CLIs
- `repositories/` — gitignored repo clones (MPs and other repos; added in Plan 4)
- `.claude/agents/` — shared agents (added in later plans)

## On project work

When you're in `content/projects/<id>/`, read that project's `CLAUDE.md` too. It's auto-generated and contains the project's objective and tool references.

## Archetypes (no types)

Projects are not labeled by archetype. If asked to investigate, draft from `content/skills/investigation/` (once it exists). For a one-pager, use `content/skills/one-pager/`. Pick based on the ask.
