---
name: login-score-events
description: >-
  Reusable SQL query actions for login scorer event analysis. Covers login score decisions,
  MITM/phishing rule detection, credential washing, drools exceptions, login counters,
  password reset abuse, application type breakdown, and fake romance friction rule monitoring.
  Uses tracking.scoreevent with scorertype = 'SCORER_LOGIN' as the primary filter.
allowed-tools: Bash
---

# Login Score Events: SQL Query Actions

Reusable Trino SQL query templates for `tracking.scoreevent` filtered to `SCORER_LOGIN`. Referenced by investigation skills (account-takeover, login-analysis, fake-account-research) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `ir2ato` (also `login`, `trustim`)
**Partition format:** `YYYY-MM-DD-00`
**Standard filter:** `scorertype = 'SCORER_LOGIN' AND scorerstage = 'CURRENT'`

---

## Queries

### Login Score Event Analysis
**When to use:** Analyze login scoring decisions by application type, password result, and challenge type for a single date. Good starting point for any login-related investigation.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT
  element_at(params, 'applicationType') as appType,
  element_at(params, 'password_result') as pwd_result,
  element_at(params, 'challenge_type') as challenge_type,
  element_at(params, 'lastChallengeTypeValidated') as lastChallenge,
  count(*) as c,
  count(distinct header.memberid) as distinct_mids
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'password_result') = 'PASS'
GROUP BY 1, 2, 3, 4
ORDER BY c DESC
LIMIT 50
```

---

### Login by Application Type
**When to use:** Break down successful logins by application type (desktop, mobile, API) on a specific date. Useful for identifying unusual app-type distribution.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT
  element_at(params, 'applicationType') as app_type,
  count(*) as c,
  count(distinct header.memberid) as distinct_mids
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'password_result') = 'PASS'
GROUP BY 1
ORDER BY c DESC
```

---

### MITM/Phishing Rule Detection
**When to use:** Detect login sessions flagged by MITM/phishing rules (Linux X11, Evilginx, ColorFish). Indicates organized phishing or MITM proxy attack.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT header.memberid, requestheader.useragent,
       element_at(params, 'js_df_screenResolution') as screenRes,
       element_at(params, 'js_df_timezoneOffset') as tzOffset,
       activatedrules, count(*) as c
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'password_result') = 'PASS'
  AND (
    contains(activatedrules, 'IMIR: MITM ATO: PWI login sessions from X11 linux based machines')
    OR contains(activatedrules, 'Incident Response: ColorFish ATO invalidate all logins via Evilginx')
    OR contains(activatedrules, 'MITM phishing attack protection layer 1 captcha')
  )
GROUP BY 1, 2, 3, 4, 5
ORDER BY c DESC
LIMIT 100
```

---

### Credential Washing Detection
**When to use:** Track logins hitting the credential washing rule (reg existing account flow with invalid member). Daily trend useful for measuring campaign volume.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct header.memberid) as distinct_mids,
       count(*) as events
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND contains(activatedrules, 'IMIR: Credential washing from reg existing account flow, invalid member')
GROUP BY 1
ORDER BY 1 ASC
```

---

### RuleSetType_GENERIC_exception Detection
**When to use:** Detect when drools is failing open (RuleSetType_GENERIC_exception). Elevated exception rates indicate scorer infrastructure issues that may leave the site unprotected.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct case when contains(activatedrules, 'RuleSetType_GENERIC_exception') then header.memberid end) as exception_mids,
       count(distinct header.memberid) as total_mids
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'password_result') = 'PASS'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Login Counter Analysis
**When to use:** Examine login counter distributions for suspicious high-count sessions indicative of credential stuffing or ATO.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

**Note:** Counter names use the NEBULA naming convention. Run this query first to discover available counter names for a given scorer:
```sql
SELECT DISTINCT key FROM (
  SELECT map_keys(counterinfo) as keys FROM tracking.scoreevent
  WHERE datepartition = '{DATE}-00' AND scorertype = 'SCORER_LOGIN' AND scorerstage = 'CURRENT'
    AND cardinality(counterinfo) > 0 LIMIT 1
) CROSS JOIN UNNEST(keys) AS t(key) ORDER BY key
```

Example query using NEBULA counter names:
```sql
SELECT
  element_at(counterinfo, 'NEBULA_CV_LOGIN_SCORER_UCV_MIGRATED_COUNTERS_SUCCESSES_PER_IP_3_FIVE_MINUTES') as login_by_ip_5m,
  element_at(counterinfo, 'NEBULA_CV_LOGIN_SCORER_UCV_MIGRATED_COUNTERS_SUCCESSES_PER_MEMBER_1_ONE_MINUTE') as login_by_mid_1m,
  element_at(counterinfo, 'NEBULA_CV_LOGIN_SCORER_UCV_MIGRATED_COUNTERS_ATTEMPTS_PER_IP_6_FIVE_MINUTES') as attempts_by_ip_5m,
  count(*) as c
FROM tracking.scoreevent
WHERE datepartition = '{DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND element_at(params, 'password_result') = 'PASS'
GROUP BY 1, 2, 3
ORDER BY c DESC
LIMIT 50
```

---

### Password Reset Abuse via Score Events
**When to use:** Track successful password resets (ONE_TIME_PASSWORD_LINK) via the scorer over time. Elevated volumes may indicate ATO via email compromise.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.loginevent` (note: `loginmethod` is a column on `tracking.loginevent`, not on `tracking.scoreevent`)

```sql
SELECT datepartition,
       count(distinct header.memberid) as distinct_mids,
       count(*) as events
FROM tracking.loginevent
WHERE datepartition >= '{START_DATE}-00'
  AND loginresult = 'PASS'
  AND loginmethod = 'ONE_TIME_PASSWORD_LINK'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Fake Romance Login from Suspicious IP Orgs
**When to use:** Track logins from accounts hitting fake romance friction rules (stricter friction for outlook/hotmail/yahoo and high-frequency IP orgs). Daily trend shows ongoing FR activity.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.scoreevent`

```sql
SELECT datepartition,
       count(distinct case when element_at(params, 'password_result') = 'PASS' then header.memberid end) as pass_count,
       count(*) as total
FROM tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND scorertype = 'SCORER_LOGIN'
  AND scorerstage = 'CURRENT'
  AND (
    contains(activatedrules, 'Incident response: 04/20/2022 Stricter friction for hotmail, mail, outlook, yahoo.com accounts - Fake Romance')
    OR contains(activatedrules, 'Incident response: 06/02/2022 Stricter friction for Fake Romance high occurance IP Orgs')
    OR contains(activatedrules, 'Incident response: 02/22/2022 Stricter friction for .ru accounts with high laser score - Fake Romance')
  )
GROUP BY 1
ORDER BY 1 ASC
```
