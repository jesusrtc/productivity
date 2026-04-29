---
name: site-traffic
description: >-
  Reusable SQL query actions for site-wide traffic anomaly investigation. Covers QPS analysis
  by hour, IPv6 block rule impact, top denied IP organizations, site speed anomaly detection,
  and suspicious external referrer traffic. Use when investigating unexpected traffic spikes,
  site performance degradation, or site-wide anomalies.
allowed-tools: Bash
---

# Site Traffic: SQL Query Actions

Reusable Trino SQL query templates for site anomaly investigation. Referenced by the site-anomaly skill instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim`
**Partition format:** `YYYY-MM-DD-00`

**Column naming:** This file uses both `tracking.*` (dot notation) and `tracking_column.*` (double-underscore). Check the table name in each query. If unsure, run `DESCRIBE {table_name}` first.

---

## Queries

### QPS by Hour
**When to use:** Measure hourly queries per second to identify traffic spikes, off-hours activity, or anomalous patterns indicative of scraping or bot waves.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking_column.userrequestevent`

```sql
WITH hourly AS (
    SELECT date_trunc('hour', from_unixtime(header__time / 1000, 'America/Los_Angeles')) as hr,
           count(*) as events
    FROM tracking_column.userrequestevent
    WHERE datepartition = '{DATE}-00'
    GROUP BY 1
)
SELECT hr,
       events,
       events / 3600.0 as qps
FROM hourly
ORDER BY hr ASC
```

---

### IPv6 Block Rule Impact
**When to use:** Track daily denial counts for a specific IPv6 block filter rule. Use to measure rule effectiveness and check for FPR concerns with IPv6 ranges.
**Parameters:** `{IPV6_RULE_NAME}` — the IPv6 block filter rule name
**Tables:** `tracking.userrequestdenialevent`

```sql
SELECT datepartition, count(*) as c
FROM tracking.userrequestdenialevent
WHERE datepartition >= daysAgo(7)
  AND denialinfo.blockfilterrulename = '{IPV6_RULE_NAME}'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Top Denied IP Organizations
**When to use:** Identify the top organizations by denial count on a specific date. Use to understand which hosting providers, ISPs, or orgs are generating the most blocked traffic.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.userrequestdenialevent`

```sql
SELECT ip_org_name(ip2str(request.ipasbytes)) as org,
       count(*) as denial_count
FROM tracking.userrequestdenialevent
WHERE datepartition = '{DATE}-00'
GROUP BY 1
ORDER BY denial_count DESC
LIMIT 30
```

---

### Site Speed Anomaly
**When to use:** Check page load time percentiles (P50, P90, P99) over a date range. Degradation in P90/P99 may indicate abuse-related server load or infrastructure issues.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.sitespeedtoplinemetricsevents`
**Permission note:** `tracking.sitespeedevent` no longer exists. The replacement tables (`tracking.sitespeedtoplinemetricsevents`, `tracking.membersitespeedsummarymetricsevent`) have restricted permissions. Request access via DataHub. Run `DESCRIBE` on the table first to check available columns, as the schema differs from the old `sitespeedevent`.

```sql
-- DESCRIBE tracking.sitespeedtoplinemetricsevents first to check available columns
-- The old sitespeedevent table no longer exists. Use the replacement table after obtaining access.
DESCRIBE tracking.sitespeedtoplinemetricsevents
```

---

### Non-LinkedIn Referrer Traffic
**When to use:** Detect traffic arriving from suspicious external referrers (not linkedin.com or linkedin.cn). May indicate phishing sites or redirect abuse sending traffic to LinkedIn.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.sitespeedtoplinemetricsevents`
**Permission note:** Same restriction as Site Speed Anomaly above. Run `DESCRIBE` first after obtaining access.

```sql
-- DESCRIBE tracking.sitespeedtoplinemetricsevents first to check for referrer columns
-- The old sitespeedevent table no longer exists.
DESCRIBE tracking.sitespeedtoplinemetricsevents
```
