---
name: login-analysis
description: >-
  Analyze login events and authentication patterns using Trino queries. Covers login method
  breakdown, 2FA analysis, password reset tracking, login result distribution, and
  authentication failure analysis. Use for login-related oncall investigations.
allowed-tools: Bash
---

# Login Analysis

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'login';`

Other headless accounts: `ir2ato`, `trustim`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking.loginevent` | Raw login events with results |
| `tracking.scoreevent` | Login scorer decisions |
| `tracking_column.scoreEvent` | Columnar login score events |
| `tracking.securitychallengeevent` | Post-login challenges |
| `prod_custservice.cs_audit_log_entries` | CS audit logs (2FA, email changes) |

## Investigation Queries

### 1. Login Result Distribution
**Action:** `login-events` → *Login Result Distribution*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use as the first query for any login oncall to establish daily baseline

### 2. Login Method Breakdown
**Action:** `login-events` → *Login Method Breakdown*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to see how successful logins are distributed across password, OTP, and third-party auth

### 3. 2FA Opt-in Analysis
**Action:** `account-activity` → *2FA Opt-in Volume (Daily)*
- Params: `{START_DATE}` — start of the date range
- Use to monitor daily 2FA enrollment trends

### 4. Password Reset Volume
**Action:** `login-events` → *Password Reset Volume*
- Params: `{START_DATE}` — start of the date range
- Use to track ONE_TIME_PASSWORD_LINK logins; spikes indicate ATO via email compromise

### 5. Login by Application Type
**Action:** `login-score-events` → *Login by Application Type*
- Params: `{DATE}` — the target date
- Use to break down successful logins by application type (desktop, mobile, API)

### 6. Login Failures by Error Type
**Action:** `login-events` → *Login Failures by Error Type*
- Params: `{DATE}` — the target date
- Use to identify what failure types dominate (BAD_PASSWORD vs LOGIN_RESTRICTED, etc.)

### 7. Suspicious User Agent Login Patterns
**Action:** `login-events` → *Suspicious User Agent Login Patterns*
- Params: `{DATE}` — the target date
- Use to find user agents associated with 100+ distinct successful login members

### 8. Email/Handle Change After Login
**Action:** `account-activity` → *Email and Handle Changes After Suspicious Activity*
- Params: `{DATE}` — the target date; `{SCHEMA}` — headless schema with suspected ATO MID table
- Use to track post-compromise account changes

### 9. Non-JS Login Detection (Ghost Lock)
**Action:** `login-events` → *Non-JS Login Detection (Ghost Lock)*
- Params: `{START_DATE}` — start of the date range
- Use to identify headless/API-based login attacks with no browser tracking

### 10. Leaked Password Cohort Correlation
**Action:** `login-events` → *Leaked Password Cohort Correlation*
- Params: `{START_DATE}` — start of the date range; `{COHORT_NAME}` — cohort table suffix
- Use to measure impact of a specific credential leak on login events

### 11. Smart Links / Phishing URL Detection
**Action:** `account-activity` → *Smart Links / Phishing URL Detection*
- Params: `{DATE}` — the target date; `{SCHEMA}` — headless schema with suspected ATO MID table
- Use to detect phishing via suspicious hashed URLs in URI metadata

## List Washing Attack Patterns

List washing = attacker logs in with exposed email/password combos to verify credential validity and/or confirm account existence. Canonical signature: low attempts per MID, high volume of distinct MIDs.

### OAuth MSFT Endpoint (Jan 2025)
- Endpoint: `/checkpoint/lg/login-submit?loginSubmitSource=OAUTH_MSFT`
- Referrer: `https://www.linkedin.com/oauth/v2/authorization`
- 100-150M daily attempts; uses 303 (success redirect) vs 500 (failure) to differentiate valid/invalid
- This endpoint is public and not covered by standard login list washing protections
- Reference: [List/email washing attack](https://docs.google.com/document/d/1JhgwnQZwKwITDF4oWayleTsUKR2a7dMeETYF_Nr0VC4/edit)

### Reg/Login Unified Endpoint
- `EXISTING_ACCOUNT_REGISTRATION` flow shows "Someone's already using that email" = information leak
- `element_at(params, 'loginFlow') = 'EXISTING_ACCOUNT_REGISTRATION'` with MID=0 is 100% abusive (0% FP)
- Attack UA: `LIAuthLibrary:44.0.* com.linkedin.LinkedIn:9.29.332 iPhone:16.0.2`
- 748M login attempts in 14 days; 133.7M successful list washes (17% unchallenged)
- Top domains: yahoo.com (698M), hotmail.com (65M), mail.com (28M)
- Attempts do NOT appear in RegistrationAttemptEvent or registrationScoreEvent
- Mitigation: Captcha for MID=0 dropped QPS from 4k to 450
- Reference: [List washing reg](https://docs.google.com/document/d/1JyjzVzNh2mMlzriaHHQUndXZjG_agc5mADyK-rWTz18/edit)

### OTP Flow List Washing
- OTP endpoint abused at 3.5k QPS for list washing
- Response time latency difference between valid/invalid accounts = timing side-channel
- FUSE 403 on null MID leaks account existence; SSP challenge from PWR scorer also leaks existence
- Reference: [OTP list washing](https://docs.google.com/document/d/19YhnNNzEXk_T49V38Ecx5M8MdSeYEXsGnF2fC_nfRNg/edit)

### Key List Washing Queries
```sql
-- Detect EXISTING_ACCOUNT_REGISTRATION abuse
SELECT element_at(params, 'loginFlow') AS loginFlow, count(*) AS c
FROM tracking.scoreeventforlogin
WHERE datepartition >= daysAgo(14)
  AND requestheader.useragent LIKE '%LinkedIn:9.29.332%'
  AND scorerstage = 'CURRENT'
GROUP BY 1 ORDER BY 2 DESC;
```

### Three-Tier Mitigation Framework
1. **UI/flow changes** requiring captcha/EPC before continuation (highest impact)
2. **IDV at PWR** for previously list-washed accounts from unfamiliar devices
3. **Signal-based detection rules** (effective but less resilient)

References: [Mitigation proposal](https://docs.google.com/document/d/17cRc-8CpyvkdVXRFd86GIT3XOqUOmzylHEGthWEluZE/edit), [List washing SOTU](https://docs.google.com/document/d/18qb1QdrZiavftpjdfwbV44G38M58VyF1XZl9_06hEQo/edit)

## Login Scoring & Defense Gaps

### Scorer Failure Detection
- 5 failure modes: scorer timeout, missing activatedrules, cookie seen race condition, RuleSetType_GENERIC_exception, missing SE but LE fired
- Detection: `loginevent le LEFT JOIN scoreeventforlogin se ON submissionid` — null SE = defense gap
- Kusto for scorer errors: `inlogsprod.westus2` / `AntiAbuse` db / `kryptonite_prelogin_integrity_war_log_event`
- LoginEvent is the Source of Truth for ATOs (not ScoreEvent — SE missing when scorer overloaded)
- Reference: [GL login scoring issues](https://docs.google.com/document/d/1ctpMWccY78s_qRe3L2rcu3hkzCARyAPCiwmPIPxZzPc/edit)

### Drools Salience Pitfall
- Stacked challenges (captcha salience -300 + EPC salience -301) break when a global override rule (salience -999) downgrades captcha
- EPC rule depends on prior challenge being captcha; when captcha removed, EPC never fires
- Reference: [Login Captcha](https://docs.google.com/document/d/1f0LdsQeRzYFYLh_OACbWksw7fvBSrHGyOYlbzwSdO90/edit)

### EPC as Information Leak
- When EPC is given during login, it confirms account existence on platform
- Attackers then credential stuff the user's email provider for email compromise ATO

## Playbook Investigation Flow (from im_playbooks: pb_loginqps.ipynb)

### Login QPS Triage
1. Monitor key metrics: Password PASS, Password FAIL (no captcha), Captcha solve rates
2. Plot QPS overlay (current vs 7 days ago) for credential washing patterns
3. Analyze attribute increases: email domains, HC, UA, referer
4. Extract HC + CC attack signature
5. Check password pass with challenge solve rates
6. Pull sample data for member behavior analysis
7. Train decision tree on positive/negative samples
8. Generate IR rules from decision tree output
9. Monitor rule performance & FP rates
10. **Key Signals**: Valid username + incorrect password = credential washing; same HC + CC across many accounts = coordinated; password PASS without challenge + subsequent activity = ATO success
11. **Decision**: Spike in FAIL with same HC/CC → credential stuffing; spike in PASS without challenge → defense gap

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `IPActivityWidget` | `IPActivityWidget(input_values=[MID1, MID2], period="30d")` | IP/search pivot — find IPs used by suspected credential-stuffing MIDs, or MIDs behind suspicious IPs |

## Tips

- Login results: `PASS`, `BAD_PASSWORD`, `EMPTY_CREDENTIALS`, `PASSWORD_INVALIDATED`, `LOGIN_RESTRICTED`, `CSRF_INVALID`
- Login methods: `PASSWORD`, `ONE_TIME_PASSWORD_LINK`, `APPLE_ID_TOKEN`, `GOOGLE_ID_TOKEN`
- `loginhandletype`: `EMAIL`, `PHONE`, `USERNAME`
- For ATO analysis, cross-reference login events with score events on `submissionid`
- 3P (third party) logins: Apple, Google tokens — check `p_status = '3P'`
- Non-JS detection: `is_li_track_with_bcookie = false` in `u_trustim.login_events`
- Leaked password cohorts: `u_tdsato.pwi_cohorts_*` tables
- Phishing URLs: `tracking.urimetadataevent` for smart links analysis
- Ghost Lock: high IP login attempts (`login_attempts_by_ip_24_hour > 15`) + no JS = strong bot signal
