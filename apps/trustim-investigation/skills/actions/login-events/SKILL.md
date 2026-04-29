---
name: login-events
description: >-
  Reusable SQL query actions for raw login event analysis. Covers login result distribution,
  login method breakdown, password reset volume, failure patterns, suspicious user agents,
  non-JS login detection, leaked password cohort correlation, and IP washing login correlation.
  Uses tracking.loginevent as the primary table.
allowed-tools: Bash
---

# Login Events: SQL Query Actions

Reusable Trino SQL query templates querying `tracking.loginevent`. These queries are referenced by investigation skills (login-analysis, account-takeover) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `login` (also `ir2ato`, `trustim`)
**Partition format:** `YYYY-MM-DD-00`

---

## Queries

### Login Result Distribution
**When to use:** Get a daily breakdown of login results (PASS, BAD_PASSWORD, etc.) over a date range to identify anomalies or spikes.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.loginevent`

```sql
SELECT datepartition,
       loginresult,
       count(*) as c,
       count(distinct header.memberid) as distinct_mids
FROM tracking.loginevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
GROUP BY 1, 2
ORDER BY 1 ASC, c DESC
```

---

### Login Method Breakdown
**When to use:** Analyze which login methods (PASSWORD, ONE_TIME_PASSWORD_LINK, GOOGLE_ID_TOKEN, APPLE_ID_TOKEN) are being used for successful logins.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.loginevent`

```sql
SELECT datepartition,
       loginmethod,
       count(*) as c,
       count(distinct header.memberid) as distinct_mids
FROM tracking.loginevent
WHERE datepartition >= '{START_DATE}-00' AND datepartition <= '{END_DATE}-00'
  AND loginresult = 'PASS'
GROUP BY 1, 2
ORDER BY 1 ASC, c DESC
```

---

### Password Reset Volume
**When to use:** Track password reset login events (ONE_TIME_PASSWORD_LINK) over time. Spikes may indicate ATO via email account compromise.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `tracking.loginevent`

```sql
SELECT datepartition,
       count(distinct header.memberid) as distinct_mids,
       count(*) as events
FROM tracking.loginevent
WHERE datepartition >= '{START_DATE}-00'
  AND loginmethod = 'ONE_TIME_PASSWORD_LINK'
  AND loginresult = 'PASS'
GROUP BY 1
ORDER BY 1 ASC
```

---

### Login Failures by Error Type
**When to use:** Analyze what types of login failures are occurring on a specific date (e.g., BAD_PASSWORD vs PASSWORD_INVALIDATED vs LOGIN_RESTRICTED).
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.loginevent`

```sql
SELECT loginresult,
       count(*) as c,
       count(distinct header.memberid) as distinct_mids
FROM tracking.loginevent
WHERE datepartition = '{DATE}-00'
  AND loginresult != 'PASS'
GROUP BY 1
ORDER BY c DESC
```

---

### Suspicious User Agent Login Patterns
**When to use:** Find user agents associated with a large number of successful logins — may indicate automation or shared tooling across many accounts.
**Parameters:** `{DATE}` — the target date (YYYY-MM-DD)
**Tables:** `tracking.loginevent`

```sql
SELECT requestheader.useragent,
       count(distinct header.memberid) as distinct_mids,
       count(*) as login_count
FROM tracking.loginevent
WHERE datepartition = '{DATE}-00'
  AND loginresult = 'PASS'
GROUP BY 1
HAVING count(distinct header.memberid) > 100
ORDER BY distinct_mids DESC
LIMIT 30
```

---

### Non-JS Login Detection (Ghost Lock)
**When to use:** Identify logins without browser tracking (headless browsers, API-based attacks). High login counter + no JS tracking = strong bot signal.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD)
**Tables:** `u_trustim.login_events`

```sql
SELECT datepartition,
       challenge_type, password_result,
       count(distinct memberid) as distinct_mids
FROM u_trustim.login_events
WHERE password_result = 'PASS'
  AND is_li_track_with_bcookie = false
  AND datepartition >= '{START_DATE}-00'
  AND login_attempts_by_ip_24_hour > 15
GROUP BY 1, 2, 3
ORDER BY 1 ASC, distinct_mids DESC
```

---

### Leaked Password Cohort Correlation
**When to use:** Check if members logging in match a known leaked password cohort. Use to measure impact of a specific credential leak.
**Parameters:** `{START_DATE}` — start date (YYYY-MM-DD); `{COHORT_NAME}` — cohort table name suffix
**Tables:** `tracking.loginevent`, `u_tdsato.pwi_cohorts_{COHORT_NAME}`

```sql
SELECT 'cohort_name' as cohort,
       count(distinct l.header.memberid) as login_mids
FROM tracking.loginevent l
WHERE l.datepartition >= '{START_DATE}-00'
  AND l.loginresult = 'PASS'
  AND l.header.memberid IN (SELECT member_id FROM u_tdsato.pwi_cohorts_{COHORT_NAME})
```

---

### IP Washing Login Correlation
**When to use:** Find members logging in from IPs known to be used for email washing or ATO. Measures successful logins from tainted IPs over time.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD)
**Tables:** `tracking.loginevent`, `u_ir2ato.tainted_ips`

```sql
SELECT datepartition,
       count(distinct case when loginresult = 'PASS' then header.memberid end) as successful_logins,
       count(distinct header.memberid) as total_mids
FROM tracking.loginevent
WHERE datepartition >= '{START_DATE}-00'
  AND datepartition <= '{END_DATE}-00'
  AND ip2str(requestheader.ipasbytes) IN (SELECT ip FROM u_ir2ato.tainted_ips)
GROUP BY 1
ORDER BY 1 ASC
```
