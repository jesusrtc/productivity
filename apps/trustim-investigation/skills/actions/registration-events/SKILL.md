---
name: registration-events
description: >-
  Reusable SQL query actions for suspicious registration investigation. Covers high-volume email
  domain detection, suspicious email/name patterns, IP-based coordinated attacks, registration
  score discrepancies, Adobe cookie (fake romance) signals, counter-based signals, and fake romance
  cluster analysis. Uses tracking.registrationevent and tracking_column.registrationEvent joined
  with tracking_column.scoreEvent.
allowed-tools: Bash
---

# Registration Events: SQL Query Actions

Reusable Trino SQL query templates for registration investigation. Referenced by investigation skills (suspicious-registrations, fake-account-research) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim` (also `register`, `ir2fake`)

**Partition formats:**
- Daily tables: `YYYY-MM-DD-00` (e.g., `2026-04-02-00`)
- Hourly tables: `YYYY-MM-DD-HH` (e.g., `2026-04-02-14`)

**IMPORTANT -- Column naming:** This file contains queries for BOTH `tracking.registrationevent` (dot notation: `email`, `header.memberid`) and `tracking_column.registrationEvent` (double-underscore: `header__memberid`, `requestheader__ip`). Never mix them. Check the table name in each query to know which column style to use. If unsure, run `DESCRIBE {table_name}` first.

**Table selection guide:**
- `tracking_hourly.scoreeventforregistration` -- use for intra-day analysis during active spikes. Partition: `YYYY-MM-DD-HH`. Retains ~2-3 days.
- `tracking.scoreeventforregistration` -- use for daily lookback (30+ days). Partition: `YYYY-MM-DD-00`. Pre-filtered to SCORER_REGISTRATION.
- `tracking_column.scoreEvent` -- use only when you need JOINs on submissionid with other columnar tables.
- `tracking.registrationevent` -- successful registrations (completions). Use for member IDs, email addresses, completion funnel.
- `tracking.registrationattemptevent` -- all registration attempts including failures. Use for attempt-to-completion rate analysis.
- `u_metrics.scraping_member_labels_union` -- scraping labels. Pipeline lag ~3-4 days. Does not effectively cover accounts under ~30 days old.

**IP enrichment UDFs** (work on any table with `requestheader.ipasbytes`):
- `ip2str(requestheader.ipasbytes)` -- binary IP to string
- `ip_country(ip2str(requestheader.ipasbytes))` -- 3-letter country code
- `ip_org_name(ip2str(requestheader.ipasbytes))` -- ISP/organization name

---

## Queries

### High-Volume Email Domain Detection
**When to use:** Find email domains with unusually high registration volume on a specific date. A quick first-pass to identify domain-based attacks.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.registrationevent`

```sql
SELECT
  split_part(email, '@', 2) AS email_domain,
  COUNT(*) AS reg_count
FROM tracking.registrationevent
WHERE datepartition = '{DATE}-00'
  AND email IS NOT NULL
GROUP BY split_part(email, '@', 2)
HAVING COUNT(*) >= 5
ORDER BY reg_count DESC
LIMIT 50
```

---

### Suspicious Email Username Patterns
**When to use:** Detect bot-generated email addresses — numeric-heavy usernames, consonant-only strings, disposable TLDs, or unusually long usernames. Use after domain detection to drill into suspicious registrations.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.registrationevent`

```sql
SELECT
  header.memberid, email, firstname, lastname,
  registrationmethod,
  from_unixtime(header.time / 1000) AS reg_time
FROM tracking.registrationevent
WHERE datepartition = '{DATE}-00'
  AND email IS NOT NULL
  AND (
    regexp_like(lower(split_part(email, '@', 1)), '[0-9]{4,}')
    OR regexp_like(lower(split_part(email, '@', 1)), '^[bcdfghjklmnpqrstvwxyz]{5,}')
    OR regexp_like(lower(split_part(email, '@', 2)),
       '\.(xyz|top|buzz|click|surf|icu|club|site|online|fun|rest|store|pw|tk|ml|ga|cf|gq)$')
    OR length(split_part(email, '@', 1)) > 30
  )
ORDER BY reg_time
LIMIT 200
```

---

### Suspicious Name Patterns
**When to use:** Detect bot-like names (first name equals last name, single character names, names containing digit sequences). Often used alongside email pattern detection.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.registrationevent`

```sql
SELECT
  header.memberid, email, firstname, lastname,
  registrationmethod,
  from_unixtime(header.time / 1000) AS reg_time
FROM tracking.registrationevent
WHERE datepartition = '{DATE}-00'
  AND (
    lower(firstname) = lower(lastname)
    OR regexp_like(firstname, '[0-9]{3,}')
    OR regexp_like(lower(firstname), '^[a-z]{1}$')
    OR regexp_like(lower(lastname), '^[a-z]{1}$')
  )
ORDER BY reg_time
LIMIT 200
```

---

### IP-Based Coordinated Registration Attack
**When to use:** Identify IPs driving high registration volumes, with breakdown of distinct user agents, locales, bcookies, header combos, and cookie combos. High volume with low distinct attributes = coordinated bot attack.
**Parameters:** `{DATE}` -- the target date (YYYY-MM-DD)
**Tables:** `tracking_column.registrationEvent`, `tracking_column.scoreEvent`
**Faster alternative:** Use the hourly table query below instead of the columnar JOIN. It is simpler and avoids the `requestheader__ip` null issue.

**WARNING:** `requestheader__ip` is frequently null in columnar tables. The columnar query below may return null IPs. Use the hourly table alternative if possible.

Columnar version (uses `requestheader__ip` which is frequently null; prefer hourly alternative below):
```sql
SELECT DISTINCT COALESCE(requestheader__ip, ip2str(requestheader__ipasbytes)) AS ip,
       count(*) AS c,
       COUNT(DISTINCT requestheader__useragent) AS distinct_ua_c,
       COUNT(DISTINCT requestheader__locale) AS distinct_locale_c,
       COUNT(DISTINCT requestheader__browserid) AS distinct_bcookie_c,
       COUNT(DISTINCT HC) AS distinct_hc_c,
       COUNT(DISTINCT CC) AS distinct_cc_c
FROM tracking_column.registrationEvent AS tr
JOIN (
    SELECT DISTINCT submissionid,
                    params['challenge_type'] as challenge_type,
                    params['sortedHeaderNames'] as HC,
                    params['sortedCookieNames'] as CC
    FROM tracking_column.scoreEvent
    WHERE datepartition = '{DATE}-00'
      AND scorerType = 'SCORER_REGISTRATION'
      AND scorerStage = 'CURRENT'
      AND params['registration_type'] = 'COLD'
      AND params['reg_input_data_validation'] = 'VALID'
) ts ON tr.submissionid = ts.submissionid
WHERE tr.datepartition = '{DATE}-00'
GROUP BY COALESCE(requestheader__ip, ip2str(requestheader__ipasbytes))
ORDER BY c DESC
LIMIT 50
```

Hourly table alternative (recommended, uses ip2str for reliable IP resolution):
```sql
SELECT ip2str(requestheader.ipasbytes) AS ip,
       ip_org_name(ip2str(requestheader.ipasbytes)) AS org,
       ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS total_attempts,
       COUNT(DISTINCT requestheader.browserid) AS distinct_bcookie_c,
       COUNT(DISTINCT requestheader.useragent) AS distinct_ua_c,
       element_at(params, 'challenge_type') AS challenge_type,
       element_at(params, 'sortedCookieNames') AS cookie_combo
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{DATE}-00' AND datepartition <= '{DATE}-23'
  AND scorerstage = 'CURRENT'
GROUP BY ip2str(requestheader.ipasbytes),
         ip_org_name(ip2str(requestheader.ipasbytes)),
         ip_country(ip2str(requestheader.ipasbytes)),
         element_at(params, 'challenge_type'),
         element_at(params, 'sortedCookieNames')
ORDER BY total_attempts DESC
LIMIT 50
```

---

### Registration Score Discrepancy
**When to use:** Find registrations where the model predicted "No Challenge" but rules did not set NONE — indicates model/rule misalignment or a potential defense gap.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `data_derived.securityreputationsystems_registration`, `tracking.scoreeventforregistration`
**Permission note:** `data_derived.securityreputationsystems_registration` has restricted permissions. Request access via DataHub (group `gr004807`).

```sql
SELECT split(memberurn, ':')[4] as mid, sr.*, activatedrules
FROM data_derived.securityreputationsystems_registration sr
JOIN tracking.scoreeventforregistration se ON sr.submissionid = se.submissionid
WHERE contains(registrationreputation.challengetypes, 'No Challenge')
  AND NOT contains(activatedrules, 'set NONE from quasar reg model')
  AND scorerstage = 'CURRENT'
  AND scorertype = 'SCORER_REGISTRATION'
  AND sr.datepartition >= '{START_DATE}-00' AND sr.datepartition < '{END_DATE}-00'
  AND se.datepartition >= '{START_DATE}-00' AND se.datepartition < '{END_DATE}-00'
LIMIT 200
```

---

### Cookie Signal Detection — Adobe/Fake Romance Pattern
**When to use:** Detect registrations with the Adobe tracking cookie pattern (`AMCVS_*` / `AMCV_*`). This is a strong fake romance signal — legitimate browsers rarely carry these specific Adobe cookies during registration.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking_column.registrationEvent`, `tracking_column.scoreEvent`
**Faster alternative:** Replace the `tracking_column.scoreEvent` subquery with `tracking.scoreeventforregistration`. Use dot notation for the subquery columns if switching.

```sql
SELECT header__memberid, email, CC, HC, challenge_type, activatedrules
FROM tracking_column.registrationEvent AS tr
JOIN (
    SELECT DISTINCT submissionid,
                    params['challenge_type'] as challenge_type,
                    params['sortedHeaderNames'] as HC,
                    params['sortedCookieNames'] as CC,
                    activatedrules
    FROM tracking_column.scoreEvent
    WHERE datepartition = '{DATE}-00'
      AND scorerType = 'SCORER_REGISTRATION'
      AND scorerStage = 'CURRENT'
      AND params['registration_type'] = 'COLD'
      AND params['reg_input_data_validation'] = 'VALID'
) ts ON tr.submissionid = ts.submissionid
WHERE tr.datepartition = '{DATE}-00'
  AND regexp_like(CC, '.*(AMCVS_14215E3D5995C57C0A495C55%40AdobeOrg.*AMCV_14215E3D5995C57C0A495C55%40AdobeOrg).*')
LIMIT 200
```

---

### Registration Counter Signals
**When to use:** Check registration counter distributions (by cookie name combos) to identify coordinated registration attacks hitting counter thresholds. High counts with few distinct cookie combos = coordinated attack.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking_column.scoreEvent`
**Faster alternative:** Use `tracking.scoreeventforregistration` if it has `counterinfo`. DESCRIBE first to verify.

```sql
SELECT
  element_at(counterinfo, 'REGISTRATION_VALID_COLD_BY_SORTED_COOKIE_NAMES_12_HOUR') as reg_by_cc_12h,
  element_at(counterinfo, 'REGISTRATION_VALID_COLD_BY_SORTED_COOKIE_NAMES_24_HOUR') as reg_by_cc_24h,
  element_at(counterinfo, 'REGISTRATION_VALID_UNRECOGNIZED_HANDLE_BY_SORTED_COOKIE_NAMES_24_HOUR') as unrec_handle_24h,
  count(*) as c
FROM tracking_column.scoreEvent
WHERE datepartition = '{DATE}-00'
  AND scorerType = 'SCORER_REGISTRATION'
  AND scorerStage = 'CURRENT'
  AND params['registration_type'] = 'COLD'
  AND params['reg_input_data_validation'] = 'VALID'
GROUP BY 1, 2, 3
ORDER BY c DESC
LIMIT 50
```

---

### Country-Level Registration Clustering
**When to use:** First query during any QPS spike. Identifies which country is driving the volume and whether the per-IP concentration is anomalous (>3x other countries).
**Parameters:** `{START_HOUR}`, `{END_HOUR}` -- hourly partition range (e.g., `2026-04-02-04`, `2026-04-02-19`)
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS total_attempts,
       COUNT(DISTINCT ip2str(requestheader.ipasbytes)) AS unique_ips,
       CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT ip2str(requestheader.ipasbytes)), 0) AS attempts_per_ip
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
GROUP BY ip_country(ip2str(requestheader.ipasbytes))
ORDER BY total_attempts DESC
LIMIT 30
```

---

### Per-IP Threshold Coverage Analysis
**When to use:** Quantifies what percentage of traffic each per-IP rate threshold would catch. Use to determine L1 drop thresholds. Run once for the anomalous country and once globally to assess false positive risk.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`, optional `{COUNTRY}` filter
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT
  CASE WHEN cnt >= 50 THEN '50+'
       WHEN cnt >= 20 THEN '20-49'
       WHEN cnt >= 10 THEN '10-19'
       WHEN cnt >= 5 THEN '5-9'
       WHEN cnt >= 3 THEN '3-4'
       ELSE '1-2' END AS attempts_bucket,
  COUNT(*) AS num_ips,
  SUM(cnt) AS total_attempts,
  SUM(nc) AS total_no_challenge
FROM (
  SELECT ip2str(requestheader.ipasbytes) AS ip,
         COUNT(*) AS cnt,
         SUM(CASE WHEN params['challenge_type'] = 'No Challenge' THEN 1 ELSE 0 END) AS nc
  FROM tracking_hourly.scoreeventforregistration
  WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
    AND scorerstage = 'CURRENT'
    -- Optional: AND ip_country(ip2str(requestheader.ipasbytes)) = '{COUNTRY}'
  GROUP BY ip2str(requestheader.ipasbytes)
)
GROUP BY 1
ORDER BY 1
```

---

### ASN/Organization Clustering
**When to use:** Find concentrated organizations driving high registration volume. High attempts/IP from a single org = VPS abuse, corporate proxy, or residential proxy botnet.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT ip_org_name(ip2str(requestheader.ipasbytes)) AS org,
       ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS total_attempts,
       COUNT(DISTINCT ip2str(requestheader.ipasbytes)) AS unique_ips,
       CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT ip2str(requestheader.ipasbytes)), 0) AS attempts_per_ip
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
GROUP BY ip_org_name(ip2str(requestheader.ipasbytes)), ip_country(ip2str(requestheader.ipasbytes))
HAVING COUNT(*) > 1000
ORDER BY attempts_per_ip DESC
LIMIT 40
```

---

### Subnet Concentration
**When to use:** Identify /24 subnets with high concentration. Subnets with >30 attempts/IP and few unique IPs = datacenter or coordinated farm. IPv4 only.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT CONCAT(
         CAST(CAST(SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 1) AS INTEGER) AS VARCHAR), '.',
         CAST(CAST(SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 2) AS INTEGER) AS VARCHAR), '.',
         CAST(CAST(SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 3) AS INTEGER) AS VARCHAR), '.0/24'
       ) AS subnet24,
       ip_org_name(ip2str(requestheader.ipasbytes)) AS org,
       ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS total_attempts,
       COUNT(DISTINCT ip2str(requestheader.ipasbytes)) AS unique_ips,
       CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT ip2str(requestheader.ipasbytes)), 0) AS attempts_per_ip,
       SUM(CASE WHEN params['challenge_type'] = 'No Challenge' THEN 1 ELSE 0 END) AS no_challenge
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
  AND ip2str(requestheader.ipasbytes) NOT LIKE '%:%'
GROUP BY 1, ip_org_name(ip2str(requestheader.ipasbytes)), ip_country(ip2str(requestheader.ipasbytes))
HAVING CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT ip2str(requestheader.ipasbytes)), 0) > 5
  AND COUNT(*) > 30
ORDER BY attempts_per_ip DESC
LIMIT 60
```

---

### Browser Fingerprint Multiplexing
**When to use:** Detect residential proxy rotation by counting unique browser fingerprints per IP. Normal users have 1-2 browsers; >5 per hour is consistent with proxy rotation.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`, optional `{COUNTRY}`
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT ip2str(requestheader.ipasbytes) AS ip,
       ip_org_name(ip2str(requestheader.ipasbytes)) AS org,
       COUNT(*) AS total_attempts,
       COUNT(DISTINCT requestheader.browserid) AS unique_browsers,
       COUNT(DISTINCT requestheader.useragent) AS unique_uas
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
  -- Optional: AND ip_country(ip2str(requestheader.ipasbytes)) = '{COUNTRY}'
GROUP BY ip2str(requestheader.ipasbytes), ip_org_name(ip2str(requestheader.ipasbytes))
HAVING COUNT(DISTINCT requestheader.browserid) > 5
ORDER BY unique_browsers DESC
LIMIT 50
```

---

### User Agent Uniformity Detection
**When to use:** Detect bot farms by checking whether user agent distribution is uniform (bot) vs power-law (organic). Run for a specific country during a spike.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`, `{COUNTRY}`
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT requestheader.useragent AS ua,
       COUNT(*) AS cnt
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
  AND ip_country(ip2str(requestheader.ipasbytes)) = '{COUNTRY}'
GROUP BY requestheader.useragent
ORDER BY cnt DESC
LIMIT 30
```
If the top 15 UAs have a standard deviation < 50 in their counts, the distribution is uniform (consistent with emulator/device farm). Organic traffic shows a steep power-law dropoff.

---

### Model Score No Challenge Gap
**When to use:** Find high-risk registrations (model score >= 0.8) that received No Challenge. Identifies scorer-layer gaps.
**Parameters:** `{START_HOUR}`, `{END_HOUR}`
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT
  CASE WHEN m.score < 0.2 THEN '0.0-0.2'
       WHEN m.score < 0.4 THEN '0.2-0.4'
       WHEN m.score < 0.6 THEN '0.4-0.6'
       WHEN m.score < 0.8 THEN '0.6-0.8'
       ELSE '0.8-1.0' END AS score_bucket,
  COUNT(*) AS cnt
FROM tracking_hourly.scoreeventforregistration
CROSS JOIN UNNEST(modelresults) AS t(m)
WHERE datepartition >= '{START_HOUR}' AND datepartition <= '{END_HOUR}'
  AND scorerstage = 'CURRENT'
  AND params['challenge_type'] = 'No Challenge'
  AND m.name = 'registration_model_frame-v16_2'
GROUP BY 1
ORDER BY 1
```

---

### Challenge Distribution Comparison
**When to use:** Compare challenge type breakdown across two time periods (e.g., spike vs post-throttle) to determine if QCS throttling changed the challenge mix.
**Parameters:** Two sets of hourly partitions
**Tables:** `tracking_hourly.scoreeventforregistration`

```sql
SELECT
  CASE WHEN datepartition >= '{PERIOD1_START}' AND datepartition <= '{PERIOD1_END}' THEN 'period1'
       WHEN datepartition >= '{PERIOD2_START}' AND datepartition <= '{PERIOD2_END}' THEN 'period2'
  END AS period,
  params['challenge_type'] AS challenge,
  COUNT(*) AS cnt
FROM tracking_hourly.scoreeventforregistration
WHERE datepartition IN (/* list both period partitions */)
  AND scorerstage = 'CURRENT'
GROUP BY 1, params['challenge_type']
ORDER BY 1, cnt DESC
```

---

### 30-Day Country Trend
**When to use:** Track daily registration attempts per country over 30 days to identify escalating patterns. Uses the daily table for longer lookback.
**Parameters:** `{START_DATE}`, `{END_DATE}`, list of countries
**Tables:** `tracking.scoreeventforregistration` (daily)

```sql
SELECT datepartition,
       ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS attempts,
       COUNT(DISTINCT ip2str(requestheader.ipasbytes)) AS unique_ips
FROM tracking.scoreeventforregistration
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorerstage = 'CURRENT'
  AND ip_country(ip2str(requestheader.ipasbytes)) IN ('ita', 'usa', 'ind', 'bra', 'nga')
GROUP BY datepartition, ip_country(ip2str(requestheader.ipasbytes))
ORDER BY datepartition, attempts DESC
```

---

### Completion Funnel
**When to use:** Measure how many registration attempts actually complete, broken down by country. Uses the daily attempt and completion tables.
**Parameters:** `{DATE}`, optional `{COUNTRY}`
**Tables:** `tracking.registrationattemptevent`, `tracking.registrationevent`

```sql
-- Attempts by country
SELECT ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS attempts
FROM tracking.registrationattemptevent
WHERE datepartition = '{DATE}-00'
GROUP BY ip_country(ip2str(requestheader.ipasbytes))
ORDER BY attempts DESC
LIMIT 20

-- Completions by country
SELECT ip_country(ip2str(requestheader.ipasbytes)) AS country,
       COUNT(*) AS completions
FROM tracking.registrationevent
WHERE datepartition = '{DATE}-00'
GROUP BY ip_country(ip2str(requestheader.ipasbytes))
ORDER BY completions DESC
LIMIT 20
```

---

### Ultrascrapper Cross-Reference
**When to use:** Check whether completed registrations from a spike appear in scraping labels. IMPORTANT: Always run a control group from a non-spike day and from multiple countries. The Ultrascrapper pipeline does not effectively cover accounts under ~30 days old, so absence of labels is inconclusive without a control group.
**Parameters:** `{REG_DATES}` (registration partitions), `{LABEL_DATE}` (scraping label partition), `{COUNTRY}`
**Tables:** `tracking.registrationevent`, `u_metrics.scraping_member_labels_union`

```sql
-- Target group: spike-day registrations from anomalous country
SELECT s.label_type, COUNT(DISTINCT s.member_id) AS cnt
FROM u_metrics.scraping_member_labels_union s
WHERE s.datepartition = '{LABEL_DATE}-00'
  AND s.member_id IN (
    SELECT CAST(r.header.memberid AS BIGINT)
    FROM tracking.registrationevent r
    WHERE r.datepartition IN ({REG_DATES})
      AND ip_country(ip2str(r.requestheader.ipasbytes)) = '{COUNTRY}'
  )
GROUP BY s.label_type ORDER BY cnt DESC

-- CONTROL GROUP: baseline registrations from multiple countries on a non-spike day
-- Use the same {LABEL_DATE} and a date at least 20 days before it
SELECT ip_country(ip2str(r.requestheader.ipasbytes)) AS country,
       COUNT(DISTINCT r.header.memberid) AS total_regs,
       COUNT(DISTINCT CASE WHEN s.member_id IS NOT NULL THEN r.header.memberid END) AS any_label,
       COUNT(DISTINCT CASE WHEN s.label_type = 'Ultrascrapper' THEN r.header.memberid END) AS ultrascrapper
FROM tracking.registrationevent r
LEFT JOIN u_metrics.scraping_member_labels_union s
  ON CAST(r.header.memberid AS BIGINT) = s.member_id AND s.datepartition = '{LABEL_DATE}-00'
WHERE r.datepartition = '{BASELINE_DATE}-00'
  AND ip_country(ip2str(r.requestheader.ipasbytes)) IN ('{COUNTRY}', 'usa', 'ind', 'bra')
GROUP BY ip_country(ip2str(r.requestheader.ipasbytes))
ORDER BY total_regs DESC
```

---

### Fake Romance Cluster by Email Pattern
**When to use:** Identify fake romance accounts by regex-matching email patterns (e.g., `firstname_lastname@outlook.com`) combined with registration scorer data and restriction status. Use to measure the scale of a known FR pattern.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking_column.registrationEvent`, `tracking_column.scoreEvent`, `data_derived.member_restrictions`
**Note:** Adjust the `regexp_like` pattern to match the current FR email pattern under investigation.

```sql
SELECT header__memberid, email, firstname, lastname,
       ma.restrictioninfo, challenge_type, HC, CC
FROM tracking_column.registrationEvent AS tr
JOIN (
    SELECT DISTINCT submissionid,
                    params['challenge_type'] as challenge_type,
                    params['sortedHeaderNames'] as HC,
                    params['sortedCookieNames'] as CC
    FROM tracking_column.scoreEvent
    WHERE datepartition BETWEEN '{START_DATE}-00' AND '{END_DATE}-00'
      AND scorerType = 'SCORER_REGISTRATION'
      AND scorerStage = 'CURRENT'
      AND params['registration_type'] = 'COLD'
      AND params['reg_input_data_validation'] = 'VALID'
) ts ON tr.submissionid = ts.submissionid
LEFT JOIN data_derived.member_restrictions ma ON tr.header__memberid = ma.member_id
WHERE tr.datepartition BETWEEN '{START_DATE}-00' AND '{END_DATE}-00'
  AND regexp_like(lower(email), '[a-z]+_[a-z]+@(outlook|hotmail).com')
```
