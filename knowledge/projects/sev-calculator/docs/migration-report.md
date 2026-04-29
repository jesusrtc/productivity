# Migration report — sev-calculator

Migrated from `/Users/jcortes/projects/sev-calculator/` on 2026-04-17.

## Converted
- project.json: 8 non-empty fields carried over
- tasks.json: 4 tasks converted from actions.json
  - 4 tasks had priority defaulted to P2
- Docs copied to docs/: one-pager.md
- Assets: no assets

## Skipped
- Worktree dirs: lipy-davi — recreate with `lab project add sev-calculator <name>` after Plan 4 worktree CLI ships
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- (none)
