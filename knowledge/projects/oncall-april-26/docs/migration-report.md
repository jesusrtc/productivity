# Migration report — oncall-april-26

Migrated from `/Users/jcortes/projects/oncall-April-26/` on 2026-04-17.

## Converted
- project.json: 7 non-empty fields carried over
- Renamed: `oncall-April-26` -> `oncall-april-26` (lowercased for lab id validator)
- tasks.json: 4 tasks converted from actions.json
  - 4 tasks had priority defaulted to P2
- Docs copied to docs/: drop-in-cold-registrations.md, investigation.md, signup-drop-apr8.md
- Assets: 12 files copied (12 from assets/, 0 root-level media)

## Skipped
- Other subdirs (not migrated): skills, notebooks
- Legacy CLAUDE.md — replaced with fresh project-scoped CLAUDE.md
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- ID renamed from `oncall-April-26` to `oncall-april-26` (lowercase required by `lab` id validator).
- Legacy `.project.json` had a `darwin` section: {"kernel_id": "78a189f0-bf5b-4205-b2f1-f904d876c84a", "proxy_user": "trustim"} — not carried into the new schema; persist elsewhere if needed.
- Legacy `.project.json` had a `metric` block (investigation anchor). Not carried into new schema.
- Legacy `.project.json` had `type: investigation`. Consider adding a tag to represent this.
