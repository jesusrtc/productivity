# Migration report — research-sev-calculator-backtesting-analysis

Migrated from `/Users/jcortes/projects/research-sev-calculator-backtesting-analysis/` on 2026-04-17.

## Converted
- project.json: 6 non-empty fields carried over
- tasks.json: 0 tasks converted from actions.json
- Docs copied to docs/: one-pager.md
- Assets: 53 files copied (53 from assets/, 0 root-level media)

## Skipped
- Worktree dirs: lipy-davi-sev-calculator-optimization — recreate with `lab project add research-sev-calculator-backtesting-analysis <name>` after Plan 4 worktree CLI ships
- Other subdirs (not migrated): resources, __pycache__, docs, skills, notebooks, incidents
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- Legacy `.project.json` had a `darwin` section: {"kernel_id": "85ec858d-e817-44e1-b654-36838c7178bd", "proxy_user": "trustim"} — not carried into the new schema; persist elsewhere if needed.
