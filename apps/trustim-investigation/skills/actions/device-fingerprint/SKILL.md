---
name: device-fingerprint
description: >-
  Reusable SQL query actions for device fingerprinting and session/identity fanout analysis.
  Covers canvas hash clustering (for ATO and fake account investigations), bcookie fanout
  from registration and login events, IP-based member fanout, and VM/automation detection.
  Used to link accounts through shared device signatures or browser cookies.
allowed-tools: Bash
---

# Device Fingerprint: SQL Query Actions

Reusable Trino SQL query templates for device fingerprint and fanout analysis. Referenced by investigation skills (account-takeover, fake-account-research, scraping-investigation) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `ir2ato` or `ir2fake` depending on investigation type
**Partition format:** `YYYY-MM-DD-00`

**Column naming:** This file uses both `tracking.*` (dot notation) and `tracking_column.*` (double-underscore). Check the table name in each query. If unsure, run `DESCRIBE {table_name}` first.

---

## Queries

### Device Fingerprint Clustering by Canvas Hash
**When to use:** Identify accounts sharing the same device fingerprint (canvas hash + WebRTC IP + RTT). RTT > 199ms indicates proxy usage. Use to cluster ATO victims or fake account groups that share tooling.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent`
**Permission note:** This table has restricted permissions for all standard headless accounts (`trustim`, `ir2ato`, `ir2fake`). Request access via DataHub at `tracking_live_daily.antiabusejavascriptdevicefeaturesevent`.
**Note:** To scope to a specific set of members, add `AND header.memberid IN (SELECT member_id FROM u_{SCHEMA}.{MID_TABLE})`.

```sql
SELECT canvas.canvashash.featurevalue as canvas_hash,
       element_at(webrealtimecommunication.candidateips, 1) AS webrtc_ip,
       networkinfo.roundtriptime.featurevalue as rtt,
       count(distinct header.memberid) as mid_count
FROM TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent
WHERE datepartition >= '{START_DATE}-00'
  AND canvas IS NOT NULL
  AND networkinfo.roundtriptime.featurevalue > 199
GROUP BY 1, 2, 3
HAVING count(distinct header.memberid) > 3
ORDER BY mid_count DESC
LIMIT 50
```

---

### Device Fingerprint Clustering for Known Members
**When to use:** Same as above, but scoped to a pre-identified set of suspected members. Shows proxy usage (RTT > 199ms) within the known cluster.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema; `{MID_TABLE}` — table of suspected member IDs
**Tables:** `TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent`
**Permission note:** This table has restricted permissions. See Canvas Hash Clustering above.

```sql
SELECT canvas.canvashash.featurevalue as canvas_hash,
       count(distinct header.memberid) as mid_count,
       count(distinct case when networkinfo.roundtriptime.featurevalue > 199 then header.memberid end) as proxy_mids
FROM TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent
WHERE datepartition >= '{START_DATE}-00'
  AND canvas IS NOT NULL
  AND header.memberid IN (SELECT member_id FROM u_{SCHEMA}.{MID_TABLE})
GROUP BY 1
HAVING count(distinct header.memberid) > 3
ORDER BY mid_count DESC
```

---

### BCookie Fanout from Registration Events
**When to use:** Find all members registered using suspicious bcookies. Attacker sessions often reuse the same browser cookie across multiple fake account registrations.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD); `{SCHEMA}` — headless schema with suspicious bcookie table
**Tables:** `tracking_column.registrationEvent`

```sql
SELECT requestheader__browserid as bcookie,
       count(distinct header__memberid) as mid_count,
       count(*) as event_count
FROM tracking_column.registrationEvent
WHERE datepartition BETWEEN '{START_DATE}-00' AND '{END_DATE}-00'
  AND requestheader__browserid IN (SELECT browserid FROM u_{SCHEMA}.suspicious_bcookies)
GROUP BY 1
ORDER BY mid_count DESC
LIMIT 100
```

---

### Phishing IP Bcookie Fanout from Login Events
**When to use:** Starting from a known phishing IP, find all bcookies used from that IP, then find all members who used those bcookies. Reveals the full scope of a phishing attack beyond the initial IP.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{PHISHING_IP}` — the known phishing IP address
**Tables:** `tracking_column.loginevent`

```sql
WITH attacker_bcookies AS (
    SELECT DISTINCT requestheader__browserid as bcookie
    FROM tracking_column.loginevent
    WHERE datepartition >= '{START_DATE}-00'
      AND requestheader__ip IN ('{PHISHING_IP}')
      AND loginresult = 'PASS'
)
SELECT bcookie, count(distinct header__memberid) as mid_count
FROM tracking_column.loginevent
WHERE datepartition >= '{START_DATE}-00'
  AND requestheader__browserid IN (SELECT bcookie FROM attacker_bcookies)
GROUP BY 1
ORDER BY mid_count DESC
```

---

### IP-Based Member Fanout
**When to use:** Find all members active on a suspicious IP range and check restriction rates. Use to size the population affected by a specific IP org or subnet, and measure how many are already restricted.
**Parameters:** `{IP_PREFIX}` — IP prefix to match (e.g., `192.168.1.`)
**Tables:** `tracking.pageviewevent`, `prod_foundation_tables.dim_member_trust_restrictions`
**Permission note:** `tracking.pageviewevent` has restricted permissions for `trustim`. Request access via DataHub or use `ir2scraping` headless account.

```sql
WITH ip_members AS (
    SELECT DISTINCT header.memberid,
           ip2str(requestheader.ipasbytes) as ip,
           ip_org_name(ip2str(requestheader.ipasbytes)) as org
    FROM tracking.pageviewevent
    WHERE datepartition >= daysAgo(7)
      AND ip2str(requestheader.ipasbytes) LIKE '{IP_PREFIX}%'
)
SELECT org,
       count(distinct im.memberid) as total_mids,
       count(distinct case when r.is_current = true then im.memberid end) as restricted
FROM ip_members im
LEFT JOIN prod_foundation_tables.dim_member_trust_restrictions r ON im.memberid = r.member_id
GROUP BY 1
ORDER BY total_mids DESC
```

---

### VM and Automation Detection via Score Events
**When to use:** Detect VMs and automation tools used during member scraping or suspicious logins. SwiftShader in vendorAndRenderer = VM/headless browser.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD); `{MEMBER_IDS}` — comma-separated list of member IDs
**Tables:** `tracking_column.scoreevent`

```sql
SELECT header__memberid,
       element_at(params, 'js_df_signals') AS signals,
       element_at(params, 'js_df_vendor') AS vendor,
       CASE WHEN strpos(COALESCE(element_at(params, 'js_df_vendor'), ''), 'SwiftShader') > 0 THEN true ELSE false END AS is_vm
FROM tracking_column.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorerType = 'SCORER_LOGIN'
  AND element_at(params, 'js_df_appName') IS NOT NULL
  AND header__memberid IN ({MEMBER_IDS})
```
