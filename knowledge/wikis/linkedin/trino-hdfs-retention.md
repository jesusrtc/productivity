---
title: "Trino / HDFS Retention Policy"
date: 2026-04-21
type: wiki
scope: org
projects: []
tags: [trino, openhouse, hive, hdfs, retention, purge-policy, data-deletion, grid]
sources:
  - "go/privacy-eng/purgepolicy (Confluence) — Setting Purge Policy for Datasets"
  - "go/lmsopenhouse (Confluence) — AE | OpenHouse Intro and Debugging Tips"
  - "go/trino/openhouse (Confluence) — OpenHouse on Trino"
  - "linkedin-multiproduct/central-policy-service — RetentionPolicyValidationResult.java"
  - "linkedin-multiproduct/hdfs-purger (Grid Security Crew)"
  - "linkedin-multiproduct/job-distribution — RetentionJob.java"
  - "linkedin-multiproduct/meta-cli/docs/pages/commands/dataPathPattern.md"
  - "linkedin-multiproduct/cbia-docs — openhouse-etl-guide.md"
  - "linkedin-multiproduct/farsight-oc — DATA_RETENTION_GUIDE.md"
  - "linkedin-multiproduct/member-first-comms-openconnect/README.md"
---

# Trino / HDFS Retention Policy

**Short answer:** Neither Trino tables nor direct-HDFS files have retention enforced by default. The owner must register a policy. When "Auto Limited Retention" (ALR) is chosen, the platform default is **23 days** on both.

## Summary

| Layer | Default retention | Who enforces it |
|---|---|---|
| Trino — OpenHouse (Iceberg, default catalog since **2026-04-08**) | None by default. If registered via `meta dataset set-retention-policy ... AUTO_LIMITED_RETENTION` with no value, platform limit = **23 days**. | OpenHouse maintenance (purger service) |
| Trino — Hive (legacy, still used for existing prod tables) | Same model. For Hive-partitioned tables under `/data/...`, ALR = **23 days** if not refreshed. | `hdfs-purger` MP + Azkaban retention jobs |
| Raw HDFS paths (`/user/<headless>/`, `/tmp/`, `/data/tracking/`, `/data/derived/`, …) | Governed by purge policy set on the path. Platform default when ALR is picked = **23 days**. | `hdfs-purger` MP |

## Trino tables

- **OpenHouse is now the default** Trino catalog for newly created tables (effective 2026-04-08); existing prod tables remain in Hive. OpenHouse data lives under `/data/openhouse/...` as Iceberg.
- **No auto-purge unless a retention policy is registered.** Set per table:
  ```sql
  ALTER TABLE openhouse.<db>.<table>
    SET POLICY (RETENTION = 720d ON COLUMN datepartition WHERE PATTERN = 'yyyy-MM-dd');
  ```
  Granularities: `h`, `d`, `m`, `y`.
- Registering with `meta dataset set-retention-policy -p openhouse --policy AUTO_LIMITED_RETENTION` and no `ALTER TABLE SET POLICY` applies the **23-day** platform default.
- **Team conventions (not platform enforcement):**
  - Dev / experimentation: 30 d
  - Training data: 180 d
  - Production models: 720 d (2 y)
  - Critical historical: 1095 d (3 y)
- **Validation rules** (`central-policy-service` → `RetentionPolicyValidationResult.java`):
  - `LIMITED_RETENTION_WITH_GREATER_RETENTION_PERIOD` — ALR must be ≤ 23 d
  - `NON_LIMITED_RETENTION_WITH_LESS_RETENTION_PERIOD` — non-ALR must be > 23 d
  - `RETENTION_PERIOD_GREATER_THAN_THRESHOLD_WITHOUT_APPROVAL` — > 90 d requires Jira approval
  - `OPENHOUSE_INSTANCE_LEVEL_NOT_SUPPORTED` — OpenHouse allows dataset-level only
- **Kyoto compaction default** (not a platform default): `OPENHOUSE_RETENTION_DURATION_DEFAULT = 13 MONTH` on `datepartition` with `yyyy-MM-dd-HH`.
- **No retention = unbounded growth** until the DB/HDFS namespace quota is hit. Called out in `cbia-docs/openhouse-etl-guide.md`.

## Files pushed directly to HDFS

- No built-in retention. Policies are registered per path via `meta pattern set-retention-policy -p hdfs -n '/path/**' -f EI ...` (see `meta-cli/docs/pages/commands/dataPathPattern.md`).
- Enforced by the **`hdfs-purger` MP** (owner: Grid Security Crew). `RetentionJob` walks configured paths and deletes files outside the retention window, respecting allow-lists.
- **Purge policy options** (`go/privacy-eng/purgepolicy`):
  - **Auto Purge (AP)** — delete on member-closure events (no time default).
  - **Auto Limited Retention (ALR)** — delete data older than N days, N ≤ 30. On HDFS: *"if a partition is not fully refreshed for 23 days or more, it will get deleted"* → **ALR default = 23 days**.
  - **Auto Limited Retention With Locking (ALRWL)** — ALR plus a lockdown window L days before deletion.
  - **Manual Limited Retention / Manual Purge** — owner-driven, require Data Deletion team approval.
  - **Purge Exempt** — legal approval; kept indefinitely.
- Platform support: HDFS supports **AP, ALR, ALRWL**. MP is ill-advised. GridTable/UMP datasets inherit from the underlying HDFS dataset.
- **No time-based default on arbitrary `/tmp/...` or `/user/<headless>/...` paths** unless the owner has registered one. E.g. `mcm-offline/openspec/specs/connected-projects-consistency-report/README.md` sets raw HDFS to 7 days — a per-MP choice, not platform.

## References

- Confluence `go/privacy-eng/purgepolicy` — canonical purge/retention policy definitions, HDFS 23-day ALR rule.
- Confluence `go/lmsopenhouse` — OpenHouse as default since 2026-04-08, `/data/openhouse` location.
- Confluence `go/trino/openhouse` — Grid-space OpenHouse/Trino integration.
- `linkedin-multiproduct/central-policy-service/.../RetentionPolicyValidationResult.java` — platform validation rules.
- `linkedin-multiproduct/hdfs-purger` (Grid Security Crew) — central HDFS purger MP.
- `linkedin-multiproduct/job-distribution/.../RetentionJob.java` — example HDFS retention job.
- `linkedin-multiproduct/meta-cli/docs/pages/commands/dataPathPattern.md` — `meta pattern` CLI reference.
- `linkedin-multiproduct/cbia-docs/docs/engineering/database/openhouse-etl-guide.md` — OpenHouse ETL / retention recipes, quota warnings.
- `linkedin-multiproduct/farsight-oc/.../DATA_RETENTION_GUIDE.md` — common retention periods.
- `linkedin-multiproduct/member-first-comms-openconnect/.../README.md` — 23-day OpenHouse auto-purge example + `SET POLICY` recipe.

## See also

- [HDFS Retention Policy — How-To Guide](./hdfs-retention-policy-guide.md)
