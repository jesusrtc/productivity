# Productivity monorepo

Single-user personal productivity suite: unified CLI (`lab`), knowledge base, and project/task state.

## Install (first time)

```
make install
```

Installs `lab` into `~/.local/bin/`. Make sure `~/.local/bin` is on your PATH.

## Spec and plans

- Design spec: `docs/superpowers/specs/2026-04-16-productivity-monorepo-design.md`
- Plans: `docs/superpowers/plans/`

## Layout

- `apps/lab/` — the unified CLI (Python)
- `content/projects/<id>/` — active projects (separate git repo, not tracked here)
- `content/{meetings,wikis,roadmaps,logs,skills}/` — content (separate git repo, not tracked here)

More in the design spec.
