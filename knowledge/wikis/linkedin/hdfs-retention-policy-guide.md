---
title: "HDFS Retention Policy — How-To Guide"
date: 2026-04-21
type: wiki
scope: org
projects: []
tags: [hdfs, trino, openhouse, hive, retention, purge-policy, meta-cli, how-to]
sources:
  - "linkedin-multiproduct/meta-cli/docs/pages/commands/dataPathPattern.md"
  - "linkedin-multiproduct/meta-cli — dataset / pattern set-retention-policy commands"
  - "go/privacy-eng/purgepolicy (Confluence) — Setting Purge Policy for Datasets"
  - "linkedin-multiproduct/central-policy-service — RetentionPolicyValidationResult.java"
  - "linkedin-multiproduct/hdfs-purger (Grid Security Crew)"
---

# HDFS Retention Policy — How-To Guide

How to set, inspect, and update the retention (purge) policy for an HDFS path, a Hive table, or an OpenHouse (Iceberg/Trino) table. See [Trino / HDFS Retention Policy](./trino-hdfs-retention.md) for the reference doc.

## Decide the policy first

Pick before running anything:

| Policy | When to use | Platform limit |
|---|---|---|
| **Auto Purge (AP)** | Member-closure driven only; no time-based expiry | n/a |
| **Auto Limited Retention (ALR)** | Default choice. Delete data older than N days | **N ≤ 30 d** (default 23 d on HDFS) |
| **ALR With Locking (ALRWL)** | ALR + lock window before deletion | same as ALR |
| **Manual Limited Retention (MLR)** | Need N > 30 d or custom cadence | > 90 d → Jira approval |
| **Manual Purge (MP)** | Owner-driven deletes | Data Deletion team approval |
| **Purge Exempt** | Must keep indefinitely | Legal approval required |

Validation (from `central-policy-service/RetentionPolicyValidationResult.java`):
- ALR must be ≤ 23 d; non-ALR must be > 23 d.
- Retention > 90 d requires Jira approval.
- OpenHouse only supports dataset-level retention (no instance-level override).

## 1. Raw HDFS paths

Registered with the `meta pattern` CLI. Enforced by the `hdfs-purger` MP.

### Inspect an existing policy

```bash
# -p <platform>  -n <path-glob>  -f <fabric: EI | PROD | etc.>
meta pattern get-retention-policy -p hdfs -n '/user/<headless>/work/**' -f EI
```

### Set (or update) a policy

```bash
# ALR — delete anything older than 23 days (platform default for HDFS)
meta pattern set-retention-policy \
  -p hdfs \
  -n '/user/<headless>/work/**' \
  -f EI \
  --policy AUTO_LIMITED_RETENTION \
  --retention-days 23

# ALRWL — 23 days + 7-day lock
meta pattern set-retention-policy \
  -p hdfs \
  -n '/user/<headless>/work/**' \
  -f EI \
  --policy AUTO_LIMITED_RETENTION_WITH_LOCKING \
  --retention-days 23 \
  --lock-days 7

# MLR — custom, e.g. 60 days (> 30 needs MLR, > 90 needs Jira approval)
meta pattern set-retention-policy \
  -p hdfs \
  -n '/data/derived/<team>/<dataset>/**' \
  -f PROD \
  --policy MANUAL_LIMITED_RETENTION \
  --retention-days 60
```

### Remove a policy

```bash
meta pattern delete-retention-policy -p hdfs -n '/user/<headless>/work/**' -f EI
```

### Notes

- `-n` is a glob. Register the narrowest pattern that covers your data so you don't accidentally purge a sibling team's path.
- Apply in **EI first** to sanity-check, then **PROD**.
- Production paths usually belong to a team namespace — confirm ownership (`meta dataset whois ...` or DataHub) before changing.
- Exclusions / allow-lists are configured in `hdfs-purger`; file a ticket with Grid Security Crew if you need a sub-path protected.

## 2. Hive tables (legacy Trino catalog, `/data/...`)

Hive tables are just HDFS paths with metadata, so path-level ALR still applies. You can also register the dataset:

```bash
meta dataset get-retention-policy -p hive -d <db>.<table> -f PROD

meta dataset set-retention-policy \
  -p hive \
  -d <db>.<table> \
  -f PROD \
  --policy AUTO_LIMITED_RETENTION \
  --retention-days 23
```

Partitioned tables under `/data/...` default to **23-day ALR** if not refreshed, when ALR is chosen.

## 3. OpenHouse / Trino tables (Iceberg, `/data/openhouse/...`)

Two surfaces — prefer **`ALTER TABLE ... SET POLICY`** for anything non-default:

### a) Register the dataset (platform default path)

```bash
meta dataset set-retention-policy \
  -p openhouse \
  -d <db>.<table> \
  -f PROD \
  --policy AUTO_LIMITED_RETENTION
# → 23-day platform default if no ALTER TABLE SET POLICY is present
```

### b) Set retention in SQL (table-level, precise)

```sql
-- 720 days on a daily-partitioned table
ALTER TABLE openhouse.<db>.<table>
  SET POLICY (
    RETENTION = 720d
    ON COLUMN datepartition
    WHERE PATTERN = 'yyyy-MM-dd'
  );

-- Hourly partitions
ALTER TABLE openhouse.<db>.<table>
  SET POLICY (
    RETENTION = 168h
    ON COLUMN datepartition
    WHERE PATTERN = 'yyyy-MM-dd-HH'
  );

-- Month / year granularities also valid
ALTER TABLE openhouse.<db>.<table>
  SET POLICY (RETENTION = 13m ON COLUMN datepartition WHERE PATTERN = 'yyyy-MM-dd');
```

### c) Inspect / remove

```sql
SHOW TBLPROPERTIES openhouse.<db>.<table>;

ALTER TABLE openhouse.<db>.<table> UNSET POLICY (RETENTION);
```

### OpenHouse gotchas

- Retention **only** supported at dataset/table level, not instance level.
- Retention > 90 d will fail validation without a Jira approval linked to the change.
- No policy set ⇒ the table grows until it hits the DB/namespace quota — this is not a theoretical concern.

## Workflow when changing retention on a live dataset

1. **Confirm ownership** — run `meta dataset whois` / check DataHub. Don't edit retention on a dataset you don't own without the owner's sign-off.
2. **Pre-flight in EI** — register the policy in EI and let `hdfs-purger` run one cycle; spot-check that the paths it would delete match expectations.
3. **Shorten retention carefully** — going from 720 d → 30 d is a destructive operation once `hdfs-purger` runs. Announce before rolling to PROD.
4. **Get approvals up front** — > 30 d → MLR, > 90 d → Jira approval, Purge Exempt → legal.
5. **Apply to PROD** — via `meta` CLI or `ALTER TABLE SET POLICY`.
6. **Verify** — `meta ... get-retention-policy` / `SHOW TBLPROPERTIES`, and watch the next purger run in the purger dashboard / MP logs.

## Quick chooser

- **"I dumped some analysis files under `/user/<me>/...`"** → ALR 23 d via `meta pattern set-retention-policy -p hdfs`.
- **"New OpenHouse table, a few weeks of history is enough"** → `ALTER TABLE ... SET POLICY (RETENTION = 30d ...)`.
- **"Production ML training data, 2 years"** → `ALTER TABLE ... SET POLICY (RETENTION = 720d ...)` + Jira approval.
- **"Must never auto-delete"** → Purge Exempt, legal approval.
- **"I just want whatever the platform enforces"** → ALR (23 d on HDFS / OpenHouse).

## References

- `meta-cli/docs/pages/commands/dataPathPattern.md` — full `meta pattern` CLI reference.
- `go/privacy-eng/purgepolicy` — policy definitions, approval matrix, platform support.
- `central-policy-service` → `RetentionPolicyValidationResult.java` — validation error codes.
- `hdfs-purger` MP (Grid Security Crew) — purger implementation and allow-list config.
- See [Trino / HDFS Retention Policy](./trino-hdfs-retention.md) for the reference wiki.
