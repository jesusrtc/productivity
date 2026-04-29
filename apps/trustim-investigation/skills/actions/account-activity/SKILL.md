---
name: account-activity
description: >-
  Reusable SQL query actions for account activity and change event analysis. Covers 2FA opt-in
  tracking, email/handle/name changes, ASTA restriction job results, WAU impact calculation,
  self-report correlation, phishing URL detection, and fake account cluster overlap analysis.
  Uses cs_audit_log_entries, memberaccountchangeevent, and related tables.
allowed-tools: Bash
---

# Account Activity: SQL Query Actions

Reusable Trino SQL query templates for account change and activity events. Referenced by investigation skills (login-analysis, account-takeover, fake-account-research, oncall-triage) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim` (also `ir2ato`, `ir2fake`)
**Partition format:** `YYYY-MM-DD-00`

---

## Queries

### 2FA Opt-in Volume (Daily)
**When to use:** Track daily 2FA enrollment events. Use to monitor post-ATO hardening behavior or the effectiveness of 2FA promotion campaigns.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `prod_custservice_column.cs_audit_log_entries`

**Note:** This table has NO `datepartition` column. Filter by `event_time` (epoch milliseconds). Use `to_unixtime(date('{DATE}')) * 1000` to convert dates. The `action_type` column does not exist; use `event_type` instead.

```sql
SELECT date_format(from_unixtime(event_time / 1000), '%Y-%m-%d') as event_date,
       count(*) as total_2fa_optin
FROM prod_custservice_column.cs_audit_log_entries
WHERE event_time >= to_unixtime(date('{START_DATE}')) * 1000
  AND event_type = 'ADD_TWO_FACTOR_AUTH'
GROUP BY 1
ORDER BY 1 ASC
```

---

### 2FA Opt-in After ATO Correlation
**When to use:** Measure how many members who opted into 2FA were also in a set of known ATO accounts. Use to assess whether ATO victims are adopting 2FA as a hardening response.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with ATO MID table
**Tables:** `prod_custservice_column.cs_audit_log_entries`

```sql
SELECT count(*) as total_2fa_optin,
       count(distinct case when acting_member_id IN (SELECT member_id FROM u_{SCHEMA}.ato_mids) then acting_member_id end) as ato_2fa
FROM prod_custservice_column.cs_audit_log_entries
WHERE event_time >= to_unixtime(date('{START_DATE}')) * 1000
  AND event_type = 'ADD_TWO_FACTOR_AUTH'
```

---

### Email and Handle Changes After Suspicious Activity
**When to use:** Track email address and handle changes by suspected ATO or fake account members. Post-compromise email changes are a strong ATO confirmation signal.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD); `{SCHEMA}` — headless schema with suspected member table
**Tables:** `prod_custservice_column.cs_audit_log_entries`

```sql
SELECT event_type, count(*) as c
FROM prod_custservice_column.cs_audit_log_entries
WHERE event_time >= to_unixtime(date('{DATE}')) * 1000
  AND event_time < to_unixtime(date('{DATE}') + interval '1' day) * 1000
  AND acting_member_id IN (SELECT member_id FROM u_{SCHEMA}.suspected_ato_mids)
GROUP BY 1
ORDER BY c DESC
```

---

### Name Change Detection for Fake Accounts
**When to use:** Track first/last name changes by suspected fake accounts — name changes after registration indicate identity evasion.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with suspected FA MID table
**Tables:** `prod_custservice_column.cs_audit_log_entries`

```sql
SELECT acting_member_id, old_value, new_value,
       from_unixtime(event_time / 1000) as change_time
FROM prod_custservice_column.cs_audit_log_entries
WHERE event_time >= to_unixtime(date('{START_DATE}')) * 1000
  AND event_type IN ('CHANGE_FIRST_NAME', 'CHANGE_LAST_NAME')
  AND acting_member_id IN (SELECT member_id FROM u_{SCHEMA}.suspected_fa_mids)
ORDER BY change_time DESC
LIMIT 200
```

---

### ASTA Restriction Results
**When to use:** Check outcomes of an Automated Short-Term Action (ASTA) restriction batch job. Shows how many members were successfully restricted, failed, or skipped.
**Parameters:** `{BATCH_NAME}` — the ASTA batch job name
**Tables:** `u_far.irasta_results`

```sql
SELECT action_status, count(*) as c
FROM u_far.irasta_results
WHERE batch_name = '{BATCH_NAME}'
GROUP BY 1
ORDER BY c DESC
```

---

### FA Cluster Overlap Analysis
**When to use:** Check how many members in a newly identified cluster are already in the known fake account dataset. High overlap confirms the cluster is catching known fakes; low overlap suggests a new or missed wave.
**Parameters:** `{SCHEMA}` — headless schema with new cluster table
**Tables:** `u_metrics.fake_account_union`

```sql
SELECT
  count(distinct a.member_id) as new_cluster_size,
  count(distinct case when b.member_id is not null then a.member_id end) as overlap_with_existing
FROM u_{SCHEMA}.new_cluster a
LEFT JOIN u_metrics.fake_account_union b ON a.member_id = b.member_id
```

---

### Self-Report Correlation for ATO
**When to use:** Measure how many self-reports (TS-RHA account compromise) correlate with a set of suspected ATO accounts. High correlation validates an ATO campaign.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with suspected ATO MID table
**Tables:** `u_metrics.dim_gco_case_osc`

```sql
SELECT count(distinct incident_id) as total_reports,
       count(distinct case when member_id IN (SELECT mid FROM u_{SCHEMA}.suspected_ato_mids) then incident_id end) as suspect_reports
FROM u_metrics.dim_gco_case_osc
WHERE date(created_time) >= date('{START_DATE}')
  AND ask_path = 'TS-RHA'
  AND category_name LIKE '%Account Compromise%'
```

---

### Smart Links / Phishing URL Detection
**When to use:** Detect members clicking suspicious hashed URLs (SmartLinks, phishing URLs) via the URI metadata event. Use to identify phishing victims or confirm a SmartLink-based ATO campaign.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD); `{SCHEMA}` — headless schema with suspected ATO MID table
**Tables:** `tracking.urimetadataevent`

```sql
SELECT header.memberid,
       hashedurl,
       count(*) as c
FROM tracking.urimetadataevent
WHERE datepartition = '{DATE}-00'
  AND header.memberid IN (SELECT member_id FROM u_{SCHEMA}.suspected_ato_mids)
GROUP BY 1, 2
ORDER BY c DESC
LIMIT 100
```

---

### Behavioral Timeline from CS Audit Logs
**When to use:** Sample 20-50 accounts from an investigation cohort to understand general behavior — login patterns, profile changes, security challenges, restrictions, email/phone changes. Use this to characterize what a cohort of accounts is doing.
**Parameters:** `{MID_LIST}` — comma-separated member IDs (sample 20-50 from your cohort)
**Tables:** `prod_custservice_column.cs_audit_log_entries`

**NOTE:** This table has NO datepartition. Filter by `event_time` (epoch milliseconds). Use `to_unixtime(date('{DATE}')) * 1000` to convert dates.

```sql
SELECT
    acting_member_id,
    event_type,
    event_time,
    notes,
    browser_id,
    session_id,
    user_agent,
    ip_address,
    ip_country(ip_address) as ip_country,
    ip_org_name(ip_address) as ip_org,
    other_target,
    new_value
FROM prod_custservice_column.cs_audit_log_entries
WHERE acting_member_id IN ({MID_LIST})
ORDER BY acting_member_id, event_time
```

---

### Behavioral Summary by Event Type (Cohort)
**When to use:** Get a high-level behavior profile for a cohort — which event types dominate, how many distinct members per event type. Good for comparing abusive vs legitimate behavior patterns.
**Parameters:** `{MID_LIST}` — comma-separated member IDs
**Tables:** `prod_custservice_column.cs_audit_log_entries`

```sql
SELECT
    event_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT acting_member_id) as unique_members,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT acting_member_id), 1) as avg_per_member
FROM prod_custservice_column.cs_audit_log_entries
WHERE acting_member_id IN ({MID_LIST})
GROUP BY event_type
ORDER BY event_count DESC
```

---

### Account Lifecycle Timeline (Single Member)
**When to use:** Deep-dive a single account's full history — registration, logins, profile edits, restrictions, challenges, password changes. Use to confirm ATO timeline or fake account behavior.
**Parameters:** `{MID}` — single member ID
**Tables:** `prod_custservice_column.cs_audit_log_entries`

```sql
SELECT
    acting_member_id,
    event_type,
    event_mode,
    notes,
    browser_id,
    session_id,
    user_agent,
    ip_address,
    ip_country(ip_address) as ip_country,
    ip_org_name(ip_address) as ip_org,
    other_target,
    new_value,
    event_time
FROM prod_custservice_column.cs_audit_log_entries
WHERE acting_member_id = {MID}
ORDER BY event_time
```

Key behavioral signals to look for:
- **ATO indicators:** `CHANGE_PASSWORD_FROM_EMAIL` followed by `UPDATE_NAME` + `ADD_EMAIL_ADDRESS` + `REMOVE_EMAIL_ADDRESS` — check if IP/UA changes between events
- **Fake account indicators:** Minimal `MEMBER_LOGIN` events, rapid `PROFILE_*_CHANGED` edits, `ADDRESS_BOOK_UPLOAD_ACCEPTED` spam, `INVITATION_FUSE_LIMIT` hits
- **Scraping indicators:** High `MEMBER_LOGIN` frequency, `TEMPORARY_HIGH_QPS_RESTRICTION_PLACED`, `SET_REHAB_RESTRICTION`
- **Session analysis:** Same `session_id` with different `browser_id` or `user_agent` = session hijack. Same `browser_id` across multiple `acting_member_id` = shared device/bot farm
- **Legitimate indicators:** Organic mix of `MEMBER_LOGIN`, `PROFILE_*_CHANGED` over weeks/months, `SOLVED_TWO_STEP_VERIFICATION_CHALLENGE`
