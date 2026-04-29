# Migration report — investigation-jss-feed

Migrated from `/Users/jcortes/projects/investigation-jss-feed/` on 2026-04-17.

## Converted
- project.json: 9 non-empty fields carried over
- tasks.json: 7 tasks converted from actions.json
  - 7 tasks had priority defaulted to P2
- Docs copied to docs/: draft-claude.md, investigation-feed-dihe.md, investigation-jss.md, one-pager.md
- Assets: 11 files copied (11 from assets/, 0 root-level media)

## Skipped
- Other subdirs (not migrated): tools, skills, notebooks, widgets
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- Legacy `.project.json` had `type: investigation`. Consider adding a tag to represent this.
