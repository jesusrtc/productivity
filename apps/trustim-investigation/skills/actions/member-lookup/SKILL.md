---
name: member-lookup
description: >-
  Reusable SQL query actions for member profile lookups, restriction checks, appeals monitoring,
  and triage utilities. Reference these named queries from any investigation skill instead of
  duplicating SQL. Covers dim_member_all, member_handles_union, dim_member_trust_restrictions,
  user_flagging, appeals, and incident metrics.
allowed-tools: Bash
---

# Member Lookup: SQL Query Actions

Reusable Trino SQL query templates for member profile and restriction data. These queries are referenced by investigation skills rather than duplicated inline.

**Trino server:** holdem
**Partition format:** `YYYY-MM-DD-00`
**Default headless account:** `trustim` (override per investigation type)

---

## Queries

### Member Handles Lookup
**When to use:** Retrieve email handles and basic info for a known member ID.
**Parameters:** `{MEMBER_ID}` — the member ID to look up
**Tables:** `u_metrics.member_handles_union`
**Permission note:** This table has restricted permissions for `trustim`. Request access via DataHub (group `ump014129`). Alternatively, use `prod_foundation_tables.dim_member_all` which includes `member_email`.

```sql
SELECT * FROM u_metrics.member_handles_union
WHERE member_id = {MEMBER_ID}
```

---

### Restriction Status Check
**When to use:** Check the full restriction history for a single member.
**Parameters:** `{MEMBER_ID}` — the member ID to look up
**Tables:** `prod_foundation_tables.dim_member_trust_restrictions`

```sql
SELECT member_id, restriction_date, unrestriction_date,
       restriction_reasons, unrestriction_reasons, is_current
FROM prod_foundation_tables.dim_member_trust_restrictions
WHERE member_id = {MEMBER_ID}
ORDER BY restriction_date DESC
```

---

### Bulk Restriction Check
**When to use:** Check restriction status for a set of members (e.g., suspected cluster). Reports how many are currently restricted vs unrestricted.
**Parameters:** `{SCHEMA}` — the headless schema holding the MID table; `{MID_TABLE}` — table name
**Tables:** `prod_foundation_tables.dim_member_trust_restrictions`

```sql
SELECT
  count(distinct member_id) as total,
  count(distinct case when unrestriction_date IS NULL AND is_current = true then member_id end) as currently_restricted,
  count(distinct case when unrestriction_date IS NOT NULL then member_id end) as unrestricted
FROM prod_foundation_tables.dim_member_trust_restrictions
WHERE member_id IN (SELECT member_id FROM u_{SCHEMA}.{MID_TABLE})
```

---

### Member Profile Enrichment
**When to use:** Retrieve comprehensive profile attributes for a member (country, industry, connections, join IP, email, restriction status).
**Parameters:** `{MEMBER_ID}` — the member ID to look up
**Tables:** `prod_foundation_tables.dim_member_all`

```sql
SELECT member_id, first_name, last_name, vanity_name,
       country_name, industry_name, headline,
       connection_count_bucket, registration_date_bucket,
       join_ip_string, member_email, is_restricted
FROM prod_foundation_tables.dim_member_all
WHERE member_id = {MEMBER_ID}
```

---

### User Flagging Check
**When to use:** Check if a member has been community-flagged (fake identity, spam, etc.).
**Parameters:** `{MEMBER_ID}` — the member ID to check
**Tables:** `u_metrics.user_flagging_v3_union`

```sql
SELECT member_id, flag_type, flag_count
FROM u_metrics.user_flagging_v3_union
WHERE member_id = {MEMBER_ID}
  AND datepartition = daysAgo(1)
```

---

### Self-Report Lookup
**When to use:** Check if a member has filed a self-report for account compromise (TS-RHA form).
**Parameters:** `{MEMBER_ID}` — the member ID to check
**Tables:** `u_metrics.dim_gco_case_osc`

```sql
SELECT incident_id, member_id, created_time, ask_path, category_name
FROM u_metrics.dim_gco_case_osc
WHERE member_id = {MEMBER_ID}
ORDER BY created_time DESC
LIMIT 20
```

---

### Appeals Monitoring
**When to use:** Track daily appeal volume and identify IMIR-related appeals over a date range.
**Parameters:** `{START_DATE}` — start of the date range (YYYY-MM-DD)
**Tables:** `u_metrics.appeals_union`

```sql
SELECT datepartition,
       count(*) as total_appeals,
       count(case when manual_note_batch_name like '%IMIR%' then 1 end) as imir_appeals
FROM u_metrics.appeals_union
WHERE datepartition >= '{START_DATE}-00'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Incident Metrics TTD and TTR
**When to use:** Calculate Time-to-Detect and Time-to-Resolve averages for completed incidents in a fiscal year.
**Parameters:** `{FY}` — fiscal year (e.g., `FY2026`)
**Tables:** `u_metrics.incident_metrics`

```sql
SELECT
  count(*) as incident_count,
  avg(ttd_minutes) as avg_ttd_min,
  avg(ttr_minutes) as avg_ttr_min
FROM u_metrics.incident_metrics
WHERE fiscal_year = '{FY}'
  AND status = 'COMPLETED'
```

---

### WAU Impact Calculation
**When to use:** Estimate Weekly Active User impact from a restriction action. Run the first query to get WAU baseline, then divide `affected_mids / wau * 100` to get impact percentage.
**Parameters:** `{DATE}` — the reference date (YYYY-MM-DD)
**Tables:** `u_metrics.wau_union`

```sql
SELECT count(distinct member_id) as wau
FROM u_metrics.wau_union
WHERE datepartition = '{DATE}-00'
-- impact_pct = affected_mids / wau * 100
```

---

### Explore Available Tables in a Schema
**When to use:** List all tables available in a user schema (e.g., `u_ir2fake`, `u_ir2ato`) when exploring what data exists.
**Parameters:** `{USERNAME}` — the schema username (without `u_` prefix)
**Tables:** `information_schema.tables`

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'u_{USERNAME}'
ORDER BY table_name
```

---

### Copy Table Between Schemas
**When to use:** Copy a table from one headless account schema to another for cross-team sharing or analysis.
**Parameters:** `{TARGET_SCHEMA}` — destination schema name; `{TABLE_NAME}` — table to copy; `{SOURCE_SCHEMA}` — source schema name
**Tables:** source and target user schemas

```sql
CREATE TABLE u_{TARGET_SCHEMA}.{TABLE_NAME} AS
SELECT * FROM u_{SOURCE_SCHEMA}.{TABLE_NAME}
```
