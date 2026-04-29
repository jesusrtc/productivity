# Migration report — project-2b

Migrated from `/Users/jcortes/projects/project-2B/` on 2026-04-17.

## Converted
- project.json: 5 non-empty fields carried over
- Renamed: `project-2B` -> `project-2b` (lowercased for lab id validator)
- tasks.json: 0 tasks (no actions.json or empty)
- Docs copied to docs/: 2B-migration-status.md (renamed from legacy `.2B.md` so it's not hidden)
- Assets: no assets

## Skipped
- Worktree dirs: airpnb, abuse-short-term-action, airp-web, inresponse-frontend, attck-alerts-airflow, trust-im-data-parity, coana-inv-frontend, TSDashRepo, lipy-invizor, airp-web-test, airp, trust-im-data-workflows, investigator-backend, account-integrity-investigation, im_playbooks, lipy-davi, airp-backend, trust-diassociation-reassociation-pipelines, samza-trust-distribution-model, flink-trust-dynamic-clustering, coana-backend, ti-attackdb, threat-service, coana-web, coana-frontend, trustinvtool, frame-feature-anti-abuse, flashpoint_ingestion, transport-udfs-antiabuse-scores — recreate with `lab project add project-2b <name>` after Plan 4 worktree CLI ships
- `.project.json`, `actions.json`, `artifacts.json`, `comments.json`, `alerts.json` — converted into `project.json` / `tasks.json`

## Notes for the user
- ID renamed from `project-2B` to `project-2b` (lowercase required by `lab` id validator).
