---
name: invitation-scoring
description: >-
  Reusable SQL query actions for invitation, messaging, and ABI (Addressbook Import) abuse
  investigation. Covers mass invitation sender detection, invitation delay rule impact,
  invitation counters, messaging abuse by type, group spam, invitation damage assessment,
  ABI flow analysis, contacts upload volume, connection break analysis, and invitation
  skew features. Uses tracking.scoreevent (SCORER_MEMBER_REQUEST), tracking.contactsuploadevent,
  tracking_column.InvitationClickEvent, and u_metrics.harm_union as primary tables.
allowed-tools: Bash
---

# Invitation Scoring: SQL Query Actions

Reusable Trino SQL query templates for invitation, messaging, and ABI abuse investigation. Referenced by investigation skills (messaging-abuse, abi-abuse, fake-account-research) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim` (also `ir2fake`, `ir2ato`)
**Partition format:** `YYYY-MM-DD-00`

**Column naming:** This file uses both `tracking.*` (dot notation) and `tracking_column.*` (double-underscore). Check the table name in each query. If unsure, run `DESCRIBE {table_name}` first.

---

## Queries

### Mass Invitation Sender Detection via Score Events
**When to use:** Find members sending unusually high invitation volumes through the scorer. Use for both messaging-abuse investigations and fake account invitation spam detection.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT header.memberid,
       count(*) as invitation_count,
       count(distinct requestheader.path) as distinct_paths
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_MEMBER_REQUEST'
  AND scorerstage = 'CURRENT'
  AND requestheader.path LIKE '%voyagerGrowthNormInvitations%'
GROUP BY 1
HAVING count(*) > 50
ORDER BY invitation_count DESC
LIMIT 100
```

---

### Mass Invitation Sender Detection via InvitationScoreEvent
**When to use:** Find fake account members sending high volumes of invitations using the InvitationScoreEvent table. Use when scoping a known fake account set.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema; `{MID_TABLE}` — table of suspected member IDs
**Tables:** `tracking.InvitationScoreEvent`

```sql
SELECT header.memberid,
       count(*) as inv_count,
       count(distinct requestheader.path) as distinct_paths
FROM tracking.InvitationScoreEvent
WHERE datepartition >= '{START_DATE}-00'
  AND header.memberid IN (SELECT member_id FROM u_{SCHEMA}.{MID_TABLE})
GROUP BY 1
HAVING count(*) > 50
ORDER BY inv_count DESC
LIMIT 100
```

---

### Invitation Delay Rule Impact
**When to use:** Track how many members are caught by invitation delay rules over a date range. Measures the reach of DELAY-decision rules.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct header.memberid) as delayed_mids,
       count(*) as total_events
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'scoreDecision') = 'DELAY'
  AND scorertype = 'SCORER_MEMBER_REQUEST'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Invitation Counter Analysis
**When to use:** Check the distribution of 24-hour invitation counters per member. High counts indicate mass inviting behavior.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT
  element_at(counterinfo, 'INVITATION_M2M_INVITATION_BY_MEMBER_24_HOUR') as inv_24h,
  count(distinct header.memberid) as mid_count
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_MEMBER_REQUEST'
  AND scorerstage = 'CURRENT'
GROUP BY 1
ORDER BY mid_count DESC
LIMIT 30
```

---

### Messaging Abuse by Type
**When to use:** Analyze messaging patterns by message type and entry point. High non-connection message volume is a spam signal.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `u_metrics.dim_member_messaging_daily`

```sql
SELECT dim_message_type,
       dim_entry_point,
       count(distinct member_id) as senders,
       sum(unique_message_between_non_connections_senders) as non_connection_msgs
FROM u_metrics.dim_member_messaging_daily
WHERE datepartition = '{DATE}-00'
GROUP BY 1, 2
ORDER BY senders DESC
LIMIT 30
```

---

### Group Spam Detection
**When to use:** Identify members making high volumes of posts in LinkedIn groups (SCORER_CONTENT_CLASSIFICATION / LINKEDIN_GROUP). High post count from a single member indicates group spam.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT header.memberid, count(*) as post_count
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00'
  AND scorertype = 'SCORER_CONTENT_CLASSIFICATION'
  AND scorerstage = 'CURRENT'
  AND usecase = 'LINKEDIN_GROUP'
GROUP BY 1
HAVING count(*) > 10
ORDER BY post_count DESC
LIMIT 50
```

---

### Invitation Damage Assessment
**When to use:** Measure harm from invitation spam — total victims and damage count from a set of suspected spammers.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema; `{SPAMMER_TABLE}` — table of suspected spammer member IDs
**Tables:** `u_metrics.harm_union`

```sql
SELECT count(distinct victim_member_id) as victims,
       sum(damage_count) as total_damage
FROM u_metrics.harm_union
WHERE datepartition >= '{START_DATE}-00'
  AND damage_type = 'RECEIVED_INVITATION'
  AND abuser_id IN (SELECT member_id FROM u_{SCHEMA}.{SPAMMER_TABLE})
```

---

### ABI Flow Analysis
**When to use:** Analyze addressbook import (ABI) flows to detect bulk invitation patterns — shows which flows, products, and subproducts are being used.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking_column.invitationclickevent`
**Permission note:** This table has restricted permissions. Request access via DataHub at `tracking_live_daily.InvitationClickEvent`.

```sql
SELECT flow, product, subproduct,
       count(*) as event_count,
       count(distinct header__memberid) as distinct_mids
FROM tracking_column.invitationclickevent
WHERE datepartition = '{DATE}-00'
  AND flow = 'ABI'
GROUP BY 1, 2, 3
ORDER BY event_count DESC
```

---

### Contacts Upload Volume
**When to use:** Detect members uploading unusually large contact lists — a key indicator of ABI abuse. Members with many upload events in a short window are suspicious.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.contactsuploadevent`

**Note:** This table does not have a `numcontactsuploaded` column. Each row represents one upload event. Count events per member as a proxy for upload volume.

```sql
SELECT header.memberid,
       count(*) as upload_count,
       count(distinct source) as distinct_sources,
       count(distinct datepartition) as active_days
FROM tracking.contactsuploadevent
WHERE datepartition >= '{START_DATE}-00'
GROUP BY 1
HAVING count(*) > 10
ORDER BY upload_count DESC
LIMIT 100
```

---

### Invitation Damage from ABI Abusers
**When to use:** Measure victim impact specifically from ABI abusers. Use the harm_union table to quantify how many unique members received unwanted invitations from ABI-identified abusers.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with ABI abuser table
**Tables:** `u_metrics.harm_union`

```sql
SELECT abuser_id,
       count(distinct victim_id) as victim_count,
       sum(damage_count) as total_damage
FROM u_metrics.harm_union
WHERE datepartition >= '{START_DATE}-00'
  AND damage_type = 'RECEIVED_INVITATION'
  AND abuser_id IN (SELECT member_id FROM u_{SCHEMA}.suspected_abi_abusers)
GROUP BY 1
ORDER BY victim_count DESC
LIMIT 100
```

---

### Connection Break Analysis Post-Invitation
**When to use:** Track connection breaks by members who received suspicious invitations — victims removing connections indicates they recognized the spam. Use to measure downstream harm.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with ABI abuser table
**Tables:** `u_secaggs.ConnectionBreakGenderStatistics`, `u_metrics.harm_union`

```sql
SELECT datepartition,
       count(*) as break_count,
       count(distinct member_id) as distinct_breakers
FROM u_secaggs.ConnectionBreakGenderStatistics
WHERE datepartition >= '{START_DATE}-00'
  AND member_id IN (SELECT victim_id FROM u_metrics.harm_union
                    WHERE damage_type = 'RECEIVED_INVITATION'
                      AND abuser_id IN (SELECT member_id FROM u_{SCHEMA}.suspected_abi_abusers))
GROUP BY 1
ORDER BY 1 ASC
```

---

### Invitation Skew Features
**When to use:** Check invitation targeting skew (e.g., gender, industry concentration) for specific members. Unusual skew indicates targeted spam campaigns.
**Parameters:** `{MEMBER_IDS}` — comma-separated list of member IDs
**Tables:** `u_secaggs.invitation_skew_features`

```sql
SELECT member_id,
       inv_sent_count,
       inv_accepted_count
FROM u_secaggs.invitation_skew_features
WHERE member_id IN ({MEMBER_IDS})
```
