# Migration report — investigation-registration

Migrated from `/Users/jcortes/projects/investigation-registration/` on 2026-04-17.

## Converted
- project.json: 8 non-empty fields carried over
- tasks.json: 11 tasks converted from actions.json
  - 11 tasks had priority defaulted to P2
- Docs copied to docs/: investigation.md, one-pager.md
- Assets: 9 files copied (9 from assets/, 0 root-level media)

## Skipped
- Other subdirs (not migrated): skills, notebooks
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- Legacy `.project.json` had a `metric` block (investigation anchor). Not carried into new schema.
