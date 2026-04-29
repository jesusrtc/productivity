---
name: sn-seats
description: >-
  Reusable SQL query actions for Sales Navigator (SN) abuse investigation. Covers SN contract
  fanout to find high-member contracts, free trial abuse detection, SN member profile enrichment,
  name change detection for evasion, and recruiter ATO InMail damage measurement.
  Uses prod_foundation_tables.dim_sales_navigator_seats as the primary table.
allowed-tools: Bash
---

# SN Seats: SQL Query Actions

Reusable Trino SQL query templates for Sales Navigator abuse investigation. Referenced by the sn-abuse skill instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `ir2fake` (also `trustim`, `jobstrust`)
**Partition format:** `YYYY-MM-DD-00`

---

## Queries

### SN Contract Fanout
**When to use:** Find SN contracts with unusually high member counts — potential clusters of fake accounts or compromised recruiter accounts sharing a contract.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `prod_foundation_tables.dim_sales_navigator_seats`

```sql
SELECT contract_id,
       count(distinct member_id) as member_count,
       min(date_format(from_unixtime(timestamps.created_time/1000, 'America/Los_Angeles'), '%Y-%m-%d')) as earliest_create
FROM prod_foundation_tables.dim_sales_navigator_seats
WHERE date_format(from_unixtime(timestamps.created_time/1000, 'America/Los_Angeles'), '%Y-%m-%d') > '{START_DATE}'
  AND role_names[1] IN ('lssAdminSeat', 'salesSeatTier2', 'salesSeatTier1')
GROUP BY 1
HAVING count(distinct member_id) > 15
ORDER BY member_count DESC
LIMIT 50
```

---

### Free Trial Abuse Detection
**When to use:** Find members on free SN trials who are also in the known fake romance dataset. Identifies fake accounts abusing the free trial to access recruiter features.
**Parameters:** none (uses last 180 days by default; adjust `daysAgo(180)` as needed)
**Tables:** `prod_foundation_tables.dim_sales_navigator_seats`, `u_ir2fake.fake_romance_union`, `u_metrics.lss_dailydash_seats_union`

```sql
SELECT distinct sn.member_id
FROM prod_foundation_tables.dim_sales_navigator_seats sn
WHERE date_format(from_unixtime(timestamps.created_time/1000, 'America/Los_Angeles'), '%Y-%m-%d') > daysAgo(180)
  AND role_names[1] IN ('lssAdminSeat', 'salesSeatTier2', 'salesSeatTier1')
  AND member_id IN (SELECT * FROM u_ir2fake.fake_romance_union)
  AND member_id IN (SELECT distinct id FROM u_metrics.lss_dailydash_seats_union WHERE paid_flag = 'free')
  AND is_contract_active = true
```

---

### SN Member Profile Enrichment
**When to use:** Enrich members on a specific SN contract with profile data, filtering for suspicious email domains (hotmail, outlook, mail.com, .ru). High concentration of these domains indicates a fake account cluster.
**Parameters:** `{CONTRACT_ID}` — the SN contract ID to investigate
**Tables:** `prod_foundation_tables.dim_sales_navigator_seats`, `prod_foundation_tables.dim_member_all`

```sql
SELECT sn.contract_id, sn.member_id,
       dim.headline, dim.first_name, dim.last_name,
       dim.default_locale, dim.member_email,
       dim.registration_first_name, dim.registration_last_name,
       dim.restriction_ts, dim.is_quality_member
FROM prod_foundation_tables.dim_sales_navigator_seats sn
JOIN prod_foundation_tables.dim_member_all dim ON sn.member_id = dim.member_id
WHERE sn.contract_id = {CONTRACT_ID}
  AND (dim.member_email LIKE '%@hotmail.com' OR dim.member_email LIKE '%@outlook.com'
       OR dim.member_email LIKE '%@mail.com' OR dim.member_email LIKE '%.ru')
```

---

### Name Change Detection in SN Contracts
**When to use:** Find SN members who changed both first and last name (registration vs current). Name changes across an entire contract indicate coordinated identity evasion.
**Parameters:** `{CONTRACT_IDS}` — comma-separated list of contract IDs
**Tables:** `prod_foundation_tables.dim_sales_navigator_seats`, `prod_foundation_tables.dim_member_all`

```sql
WITH changed_names AS (
    SELECT member_id, first_name, last_name,
           registration_first_name, registration_last_name,
           contract_id, restriction_ts
    FROM prod_foundation_tables.dim_sales_navigator_seats sn
    JOIN prod_foundation_tables.dim_member_all dim ON sn.member_id = dim.member_id
    WHERE contract_id IN ({CONTRACT_IDS})
      AND UPPER(registration_last_name) <> UPPER(last_name)
      AND UPPER(registration_first_name) <> UPPER(first_name)
)
SELECT contract_id,
       count(distinct member_id) as name_changed_mids,
       count(distinct case when restriction_ts IS NOT NULL then member_id end) as restricted
FROM changed_names
GROUP BY 1
ORDER BY name_changed_mids DESC
```

---

### Recruiter ATO with InMail UMI
**When to use:** Measure InMail damage from compromised recruiter accounts. Joins ATO events with abuse damage to count unique victims within a 7-day window of each ATO event.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `u_metrics.ato_volume_union`, `u_metrics.abuse_damage_ato_union`

```sql
WITH recruiter_ato AS (
    SELECT DISTINCT memberid,
           DATE(SUBSTR(datepartition,1,10)) AS ato_date,
           DATE(SUBSTR(datepartition,1,10)) - INTERVAL '6' DAY AS ato_7d_start
    FROM u_metrics.ato_volume_union
    WHERE num_recruiter = 1 AND num_fp = 0
      AND datepartition >= '{START_DATE}-00'
)
SELECT count(distinct ato.memberid) as ato_recruiters,
       count(distinct dmg.victim_id) as total_umi
FROM recruiter_ato ato
LEFT JOIN u_metrics.abuse_damage_ato_union dmg
    ON ato.memberid = dmg.abuser_id
    AND dmg.datepartition BETWEEN ato.ato_7d_start AND ato.ato_date
WHERE dmg.damage_type = 'RECEIVED_MESSAGE'
```
