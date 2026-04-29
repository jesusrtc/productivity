# Migration report — davi-trino-perf

Migrated from `/Users/jcortes/projects/davi-trino-perf/` on 2026-04-17.

## Converted
- project.json: 7 non-empty fields carried over
- tasks.json: 7 tasks converted from actions.json
  - 7 tasks had priority defaulted to P2
- Docs copied to docs/: specs.md
- Assets: no assets

## Skipped
- Worktree dirs: lipy-davi — recreate with `lab project add davi-trino-perf <name>` after Plan 4 worktree CLI ships
- Other subdirs (not migrated): notebooks
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- (none)
