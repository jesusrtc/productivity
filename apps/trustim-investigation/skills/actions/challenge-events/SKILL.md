---
name: challenge-events
description: >-
  Reusable SQL query actions for security challenge analysis. Covers challenge volume by type,
  captcha solve rates, JavaScript challenge pass-through, phone challenge with Telesign risk scores,
  email pin challenge flow, SSP/SHC eligibility, IDV metrics, email bounce detection,
  Arkose bot detection, and IDV appeal verification.
  Uses tracking.securitychallengeevent as the primary table.
allowed-tools: Bash
---

# Challenge Events: SQL Query Actions

Reusable Trino SQL query templates for security challenge analysis. Referenced by the challenge-research skill instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim`
**Partition format:** `YYYY-MM-DD-00`

**Column naming:** This file uses both `tracking.*` (dot notation) and `tracking_column.*` (double-underscore). Check the table name in each query. If unsure, run `DESCRIBE {table_name}` first.

---

## Queries

### Challenge Volume by Type
**When to use:** Get a daily breakdown of all challenge events by type and outcome. Use as the first query when investigating challenge anomalies or defense effectiveness.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.securitychallengeevent`

```sql
SELECT datepartition,
       challengetype,
       validationresult,
       eventtype,
       count(*) as c
FROM tracking.securitychallengeevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
GROUP BY 1, 2, 3, 4
ORDER BY 1 ASC, c DESC
```

---

### Captcha Challenge Solve Rate
**When to use:** Track daily captcha solve rates over a date range. A drop in solve rates may indicate bots bypassing captcha; a spike may indicate farm-based solving.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.securitychallengeevent`

```sql
SELECT datepartition,
       count(*) as total_challenges,
       count(case when validationresult = 'USER_RESPONSE_CORRECT' then 1 end) as solved,
       count(case when validationresult = 'USER_RESPONSE_INCORRECT' then 1 end) as failed
FROM tracking.securitychallengeevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND challengetype = 'CAPTCHA_CHALLENGE'
  AND eventtype = 'SUBMIT_CHALLENGE'
GROUP BY 1
ORDER BY 1 ASC
```

---

### JavaScript Challenge Analysis
**When to use:** Check JS challenge pass-through rate over time. Sudden increases in passes (bots solving JS challenges) indicate evasion.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.securitychallengeevent`

```sql
SELECT datepartition,
       count(*) as total,
       count(case when validationresult = 'USER_RESPONSE_CORRECT' then 1 end) as passed,
       count(case when validationresult != 'USER_RESPONSE_CORRECT' then 1 end) as blocked
FROM tracking.securitychallengeevent
WHERE datepartition >= '{START_DATE}-00'
  AND challengetype = 'JAVASCRIPT_CHALLENGE'
  AND eventtype = 'SUBMIT_CHALLENGE'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Phone Challenge with Telesign Risk Score
**When to use:** Analyze phone challenges enriched with carrier and Telesign risk data, broken down by IP country. High-risk carriers with specific countries may indicate SIM-swap or IRSF fraud.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.phonescoreevent`

```sql
SELECT
  telesignscoreresponse[17] as carrier,
  telesignscoreresponse[18] as risk_score,
  ip_country(ip2str(reputationdata.georeputation.ipderivedsubnet)) as ip_country,
  count(distinct submissionid) as c
FROM tracking.phonescoreevent
WHERE datepartition >= '{START_DATE}-00'
  AND scorerstage = 'CURRENT'
GROUP BY 1, 2, 3
ORDER BY c DESC
LIMIT 50
```

---

### Email Pin Challenge Flow
**When to use:** Track how many members are challenged with email pin and how many successfully solve it per day. Low solve rates may indicate bot accounts unable to access the email inbox.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct header.memberid) as mids_challenged,
       count(distinct case when element_at(params, 'lastChallengeTypeValidated') = 'EMAIL_PIN' then header.memberid end) as email_pin_solved
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'challenge_type') != 'No Challenge'
GROUP BY 1
ORDER BY 1 ASC
```

---

### SSP/SHC Challenge Eligibility After Email Pin
**When to use:** Determine how many members become eligible for SSP (Secondary Security Protocol) after resolving email pin challenge. Used to tune SSP trigger thresholds.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT count(*) as total,
       count(case when element_at(params, 'lastChallengeTypeValidated') = 'EMAIL_PIN'
                   AND (element_at(params, 'scoreDecision') = 'ACCEPT'
                        OR (element_at(params, 'scoreDecision') = 'CHALLENGE' AND element_at(params, 'challenge_type') = 'No Challenge'))
                  then 1 end) as eligible_for_ssp
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
```

---

### IDV Metrics
**When to use:** Track Identity Verification funnel metrics (shown → uploaded → approved) over time. Use to assess IDV effectiveness and approval rates.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{IDV_METRICS_TABLE}` — the specific IDV metrics table
**Tables:** IDV-specific metrics table (confirm table name with `DESCRIBE`)

```sql
SELECT datepartition,
       sum(num_member_showed_idv) as showed_idv,
       sum(num_idv_uploaded_image) as uploaded,
       sum(num_idv_approved_by_cv) as approved
FROM {IDV_METRICS_TABLE}
WHERE datepartition >= '{START_DATE}-00'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Email Bounce Detection
**When to use:** Identify registrations with bounced emails — a strong fake account signal. Hard bounces (classification 10) mean the email address is invalid.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.emailbounceevent`, `tracking_column.registrationEvent`
**Note:** Bounce classifications: `10` = hard bounce (invalid mailbox), `1` = undetermined, `40` = generic bounce

```sql
SELECT bounce.bounceclassification, count(*) as c
FROM tracking.emailbounceevent bounce
JOIN tracking_column.registrationEvent re ON bounce.header.memberid = re.header__memberid
WHERE bounce.datepartition >= '{START_DATE}-00'
  AND re.datepartition >= '{START_DATE}-00'
GROUP BY 1
ORDER BY c DESC
```

---

### Arkose Suspicious Activity Detection
**When to use:** Track registrations and logins flagged by Arkose bot detection. `suspiciousactivities IS NOT NULL` means Arkose detected bot-like behavior.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.ArkoseLabsRealTimeLoggingEvent`
**Permission note:** This table has restricted permissions. Request access via DataHub if needed.

```sql
SELECT datepartition,
       count(*) as total,
       count(case when suspiciousactivities IS NOT NULL then 1 end) as arkose_suspicious
FROM tracking.ArkoseLabsRealTimeLoggingEvent
WHERE datepartition >= '{START_DATE}-00'
GROUP BY 1
ORDER BY 1 ASC
```

---

### IDV Appeal Verification
**When to use:** Track identity verification outcomes for members in an appeal flow. Use to measure appeal success rates and verification vendor distribution.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{SCHEMA}` — headless schema with appeal MID table
**Tables:** `tracking.idverificationv2event`

```sql
SELECT verificationstatus, vendortype, source, count(*) as c
FROM tracking.idverificationv2event
WHERE datepartition >= '{START_DATE}-00'
  AND header.memberid IN (SELECT member_id FROM u_{SCHEMA}.appeal_mids)
GROUP BY 1, 2, 3
ORDER BY c DESC
```
