---
title: "Roadmap: DAVI Alerting Migration"
date: 2026-04-03
type: roadmap
scope: org
projects: [davi]
tags: [roadmap, davi, alerting, scraping, trust-im, widgets]
people: [jcortes]
sources: ["https://docs.google.com/document/d/1Kp7ZSSpPuhFuA-FNjBcymzMNqUc1K110PnR9XhoPnek/edit"]
---

# Roadmap: DAVI Alerting Migration

Migrating the monolithic Trust IM scraping alert into independent per-cohort notebooks using DAVI widgets. Design spec: [Scraping Alerting Revamp One-Pager](https://docs.google.com/document/d/1Kp7ZSSpPuhFuA-FNjBcymzMNqUc1K110PnR9XhoPnek/edit)

## Phase 1: DAVI Widgets + Egress Notebooks (DONE)

New DAVI widgets for alerting infrastructure and Egress cohort split.

- [x] `QueryWidget` — SQL execution with retry + exponential backoff
- [x] `DataFreshnessWidget` — upstream table freshness validation
- [x] `TrustAlertBatchWidget` — batch AlertPlotWidget execution with error capture
- [x] `TrustAlertIrisWidget` — Iris incident creation with `is_prod` toggle
- [x] `TrustAlertExecutionLogWidget` — append-only execution logging to Trino
- [x] `AlertPlotWidget` backward-compat fix (`is_alert`, `df`, `title`, `alert_type`, `alert_params`)
- [x] 7 per-cohort Egress notebooks (restricted, total, labeled, labeled-malicious, registered, registered-suspicious, becdt)
- [x] PRs merged: lipy-davi#209, lipy-davi#210, im_playbooks#503

## Phase 2: Darwin E2E Testing (DONE — 2026-04-03)

Validated full pipeline end-to-end on Darwin using `darwin_dev.install()` and `davi_runner.py`.

- [x] Install dev davi on Darwin and verify `is_dev_env()` works
- [x] Test `DataFreshnessWidget` against live `u_tdsauto.data_egression_by_cohorts`
- [x] Test `QueryWidget` retry logic against live Trino (3 retries, exponential backoff confirmed)
- [x] Verify `AlertPlotWidget` `is_alert`/`df` properties work in Darwin (#209 fix verified)
- [x] Run `TrustAlertBatchWidget` with real alert widgets (8 widgets, restricted cohort)
- [x] Verify `TrustAlertIrisWidget` hits test plan (`is_prod=False`) — fired to `#alerting-framework`
- [x] Verify `TrustAlertExecutionLogWidget` writes START/END to `u_trustim.alert_execution_log`
- [x] Full E2E run of `alert-scraping-egress-restricted.ipynb` pipeline
- [x] Reset dev install and verify original version restored
- [x] Fix irisclient constructor bug (wrong args) and add dependency
- [x] Create `%%safeql` cell magic with retry, variable substitution, `<<` compat
- [x] Create `u_trustim.alert_execution_log` table (didn't exist)
- [x] Set 7 notebooks to testing mode (`on_stale="warn"`, `is_prod=False`, `%%safeql`)
- [x] PRs: lipy-davi#211, im_playbooks#506

## Phase 2.5: Iris Key Security + Darwin Remote Execution (NEXT)

### Iris API Key in HDFS

Store the `liairp` Iris API key in HDFS instead of passing it as a scheduler parameter (visible to stakeholders). DAVI reads the key at runtime from a known HDFS path.

- [ ] Upload Iris API key to HDFS path (e.g. `hdfs:///user/trustim/secrets/iris_api_key`)
- [ ] Add key-reading utility in DAVI (`TrustAlertIrisService` reads from HDFS if `IRIS_API_KEY` env var is empty)
- [ ] Remove `api_key` parameter from Darwin scheduler configs
- [ ] Document the HDFS path and access permissions

### Darwin Remote Execution in DAVI

Build Darwin remote execution into DAVI itself so widgets can be tested on Darwin from a local dev environment. Document the learnings from E2E testing.

- [ ] Integrate `davi_runner.py` pattern into DAVI (setup, start, run, stop lifecycle)
- [ ] Document Darwin infrastructure learnings:
  - Proxy auth: `jupyter-proxy` with DVToken, auto-refresh on 401/403
  - Pod lifecycle: `GET /k8s/hub/login`, status codes (200/404/503/502/504)
  - Two auth cookies: `darwin-play-session` (CHP) vs `darwin_dv_token_session` (Hub)
  - Kernel management: `%remote --connect --new`, reconnect on 405 timeout
  - Race condition: proxy must be ready before kernel connects
- [ ] Add `davi darwin setup` / `davi darwin start` / `davi darwin run` CLI commands
- [ ] Support `%%safeql` magic over remote Darwin kernels

### Dev Widget Testing Workflow

Automated workflow to test widget changes on Darwin before release. Same pattern we used manually with `darwin_dev.install(branch)`.

- [ ] `davi darwin test-branch <branch>` — clone repo on Darwin pod, install dev branch, run tests
- [ ] `davi darwin reset` — restore original `linkedin.davi` from backup
- [ ] Auto-generate test notebook (.ipynb) with timestamped cells and outputs
- [ ] Push test notebook to Darwin folder via Darwin API (evidence of testing)
  - Use Darwin file upload API to save `.ipynb` to `darwin.prod.linkedin.com/user/{user}/`
  - Notebook serves as audit trail: what was tested, what passed/failed
- [ ] `davi darwin publish <notebook> --folder <path>` — upload local notebook to Darwin

## Phase 3: Voyager, GraphQL, Identity Dash Notebooks

Split remaining alert categories from the monolithic notebook into per-cohort notebooks.

- [ ] Voyager cohort notebooks
- [ ] GraphQL cohort notebooks
- [ ] Identity Dash cohort notebooks
- [ ] Remove all split categories from monolithic notebook

## Phase 4: Production Rollout

- [ ] Replace hardcoded `notify_to="jcortes"` — decide on proper error notification: team DL, Iris plan, or DAVI-managed alerting
- [ ] Toggle `is_prod=True` on validated cohort notebooks
- [ ] Schedule notebooks via Darwin cron
- [ ] Monitor execution logs in `u_trustim.alert_execution_log`
- [ ] Decommission monolithic `alert-member-scraping.ipynb`
