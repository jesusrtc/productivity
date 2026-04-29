---
name: rule-performance
description: >-
  Reusable SQL query actions for trust/safety rule performance analysis. Covers rule trigger
  volume tracking, false positive rate (FPR) calculation, unique member impact (UMI) calculation,
  distribution score analysis for bot detection, drools exception monitoring, and LIX experiment
  impact measurement. Use when tuning rules or assessing rule coverage and precision.
allowed-tools: Bash
---

# Rule Performance: SQL Query Actions

Reusable Trino SQL query templates for rule performance tracking and tuning. Referenced by the rule-tuning skill instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim`
**Partition format:** `YYYY-MM-DD-00`

**Column naming:** This file uses both `tracking.*` (dot notation) and `tracking_column.*` (double-underscore). Check the table name in each query. If unsure, run `DESCRIBE {table_name}` first.

---

## Queries

### Rule Trigger Volume (Daily)
**When to use:** Track how often a specific rule fires over a date range. Use to confirm deployment, measure volume trends, or detect rule degradation.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD); `{RULE_NAME}` — exact rule name string; `{SCORER_TYPE}` — e.g., `SCORER_LOGIN`
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(*) as triggers,
       count(distinct header.memberid) as distinct_mids
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorerstage = 'CURRENT'
  AND contains(activatedrules, '{RULE_NAME}')
GROUP BY 1
ORDER BY 1 ASC
```

---

### FPR (False Positive Rate) Calculation
**When to use:** Calculate false positive rate for a rule by comparing triggered members against currently restricted members. FPR = 1 - Precision. Target < 5% for production rules.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD); `{RULE_NAME}` — exact rule name string
**Tables:** `tracking.scoreevent`, `prod_foundation_tables.dim_member_trust_restrictions`

```sql
WITH rule_mids AS (
    SELECT distinct header.memberid as mid
    FROM tracking.scoreevent
    WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
      AND scorerstage = 'CURRENT'
      AND contains(activatedrules, '{RULE_NAME}')
),
restricted AS (
    SELECT distinct member_id
    FROM prod_foundation_tables.dim_member_trust_restrictions
    WHERE is_current = true
      AND member_id IN (SELECT mid FROM rule_mids)
)
SELECT
  (SELECT count(*) FROM rule_mids) as total_triggered,
  (SELECT count(*) FROM restricted) as restricted_count,
  cast((SELECT count(*) FROM restricted) as double) / cast((SELECT count(*) FROM rule_mids) as double) as precision,
  1.0 - cast((SELECT count(*) FROM restricted) as double) / cast((SELECT count(*) FROM rule_mids) as double) as fpr
```

---

### UMI (Unique Member Impact) Calculation
**When to use:** Calculate the daily count of unique members impacted (challenged, restricted, or delayed) by a scorer type over a date range. Use to measure defense coverage and WoW trends.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD); `{SCORER_TYPE}` — e.g., `SCORER_LOGIN`, `SCORER_REGISTRATION`
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct header.memberid) as umi
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorerstage = 'CURRENT'
  AND scorertype = '{SCORER_TYPE}'
  AND element_at(params, 'challenge_type') != 'No Challenge'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Distribution Score Analysis
**When to use:** Detect coordinated bot activity using distribution scoring on user agent patterns. Distribution score > 0.8 indicates concentrated (bot-like) traffic. Requires loading the antiabuse UDF JAR.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD); `{TARGET_UA}` — the user agent string to analyze
**Tables:** `tracking_column.userrequestevent`

```sql
ADD JAR ivy://com.linkedin.transport-udfs-antiabuse-scores:transport-udfs-antiabuse-scores:0.0.9?classifier=hive;
CREATE TEMPORARY FUNCTION distribution_score AS 'com.linkedin.stdudfs.antiabuse.hive.DistributionScore';

WITH ua_data AS (
    SELECT request__useragent,
           date_trunc('minute', from_unixtime(header__time / 1000, 'America/Los_Angeles')) as minutes
    FROM tracking_column.userrequestevent
    WHERE datepartition = '{DATE}-00'
),
ua_buckets AS (
    SELECT request__useragent, minutes,
           cast(count(*) as int) as cnt
    FROM ua_data
    WHERE request__useragent = '{TARGET_UA}'
    GROUP BY 1, 2
)
SELECT request__useragent,
       distribution_score(array_agg(cnt order by minutes)) / 10000.0 as dist_score
FROM ua_buckets
GROUP BY 1
```

---

### Drools Exception Monitoring
**When to use:** Track RuleSetType_GENERIC_exception rate for a scorer type over time. Elevated rates indicate the drools rules engine is failing open — a critical security gap.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD); `{SCORER_TYPE}` — e.g., `SCORER_LOGIN`
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(*) as total_events,
       count(distinct case when contains(activatedrules, 'RuleSetType_GENERIC_exception') then header.memberid end) as exception_mids,
       count(distinct header.memberid) as total_mids
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorertype = '{SCORER_TYPE}'
  AND scorerstage = 'CURRENT'
GROUP BY 1
ORDER BY 1 ASC
```

---

### LIX Experiment Impact
**When to use:** Check member counts per variant for a LIX experiment. Use to verify experiment ramp and ensure balanced treatment/control splits.
**Parameters:** `{EXPERIMENT_ID}` — the LIX experiment ID; `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `data_derived_column.lixexperimentassignmentdata_daily`
**Permission note:** This table has restricted permissions. Request access via DataHub (group `gr004899`).

```sql
SELECT variant, count(distinct memberId) as member_count
FROM data_derived_column.lixexperimentassignmentdata_daily
WHERE experimentId = {EXPERIMENT_ID}
  AND datepartition = '{DATE}-00'
GROUP BY 1
```
