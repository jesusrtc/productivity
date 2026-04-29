---
name: common-reference
description: >-
  Comprehensive reference for TrustIM investigation tables, UDFs, and common patterns.
  Use as a lookup when you need to find the right table, function, or query pattern
  for any investigation type.
allowed-tools: Bash
---

# TrustIM Common Reference

## IMPORTANT: Query Construction Guidelines

**The queries in all skills are REFERENCE TEMPLATES only.** For actual investigations:

1. **Never mix tracking table column styles.** `tracking.*` tables use dot notation (`header.memberid`). `tracking_column.*` tables use double-underscore (`header__memberid`). See the "Tracking Table Column Naming" section below for the full reference. **If there is ever any discrepancy or uncertainty about column names, run `DESCRIBE {table_name}` first to verify the actual schema.**
2. **Always check the table schema first** before running a query:
   ```sql
   DESCRIBE {table_name}
   ```
3. **Construct the actual query** based on the current schema, not the template — columns may have changed.
4. **Always aggregate and GROUP BY** to minimize data returned. Never SELECT * on large tables without LIMIT.
5. **Use COUNT, COUNT(DISTINCT ...), approx_percentile()** to summarize rather than returning raw rows.
6. **Always filter on datepartition** to avoid full table scans.
7. **Use LIMIT** on all exploratory queries (max 50-100 rows).
8. **For missing context**, use the Captain MCP tools:
   - `unified_context_search` to search wikis, Slack, JIRA for investigation context
   - `search_confluence_content` for runbooks and playbooks
   - `get_confluence_page` for specific documentation
   - `read_google_docs_document` for investigation docs
   - Ask the user if context is still insufficient

## Trino Setup

**Server:** holdem

**Preamble (always required):**
```sql
SET SESSION li_authorization_user = '{HEADLESS_ACCOUNT}';
```

**Partition format:** `YYYY-MM-DD-00` (e.g., `2026-03-11-00`). Dates are in **US Pacific time** by default.

## Headless Accounts

| Account | Use Case |
|---------|----------|
| `trustim` | General trust investigations |
| `ir2ato` | Account takeover investigations |
| `ir2fake` | Fake account investigations |
| `ir2scraping` | Scraping investigations |
| `tdsfake` | TDS fake accounts |
| `tdsfraud` | TDS fraud |
| `tdssample` | TDS sampling |
| `jobstrust` | Jobs trust |
| `login` | Login investigations |
| `register` | Registration investigations |
| `far` | Fake account research |
| `scrapeds` | Scraping data science |

## CRITICAL: Tracking Table Column Naming

LinkedIn has two versions of most tracking tables. **Never mix column styles across tables.**

| Schema | Example Table | Column Style | Examples |
|--------|--------------|--------------|----------|
| `tracking.*` | `tracking.registrationevent` | **Dot notation** (nested structs) | `header.memberid`, `email`, `requestheader.useragent`, `ip2str(requestheader.ipasbytes)` |
| `tracking_column.*` | `tracking_column.registrationEvent` | **Double-underscore** (flattened) | `header__memberid`, `email`, `requestheader__useragent`, `requestheader__ip` |

**Key differences:**
- `tracking.*` stores IPs as bytes → use `ip2str(requestheader.ipasbytes)` to get a string, then `ip_country()` / `ip_org_name()` on the result
- `tracking_column.*` stores IPs as strings → use `requestheader__ip` directly with `ip_country()` / `ip_org_name()`
- `tracking.*` uses `header.memberid` (dot). `tracking_column.*` uses `header__memberid` (double underscore)
- `tracking.*` uses `email` directly. `tracking_column.*` also uses `email` (no prefix)
- Use `tracking_column.*` when you need to JOIN on `submissionid` (it's a top-level column). Use `tracking.*` for simpler queries.

**Common mistakes to avoid:**
- `tracking.registrationevent` with `header__memberid` → WRONG (dot table, underscore column)
- `tracking_column.registrationEvent` with `header.memberid` → WRONG (underscore table, dot column)
- `tracking.registrationevent` with `requestheader__ip` → WRONG (dot table, underscore column)
- `ip_country(requestheader.ipasbytes)` → WRONG (need `ip2str()` wrapper for bytes)

**When in doubt, DESCRIBE the table first.** If you are unsure which column style a table uses, run `DESCRIBE {table_name}` before constructing your query. This takes 1 second and prevents broken queries.

## Core Investigation Tables

### Tracking Events (Daily)
Partition format: `YYYY-MM-DD-00`. Retains 30+ days.

| Table | Purpose |
|-------|---------|
| `tracking.loginevent` | Login events with results |
| `tracking.registrationevent` | Successful registrations |
| `tracking.registrationattemptevent` | All registration attempts (includes failures) |
| `tracking.scoreevent` | Score events (all scorer types) |
| `tracking.scoreeventforlogin` | Login-specific score events |
| `tracking.scoreeventforregistration` | **Preferred** for registration scoring (daily). Pre-filtered to SCORER_REGISTRATION. |

### Tracking Events (Hourly)
Partition format: `YYYY-MM-DD-HH` (e.g., `2026-04-02-14`). Retains ~2-3 days. Use for intra-day analysis during active spikes.

| Table | Purpose |
|-------|---------|
| `tracking_hourly.scoreeventforregistration` | Hourly registration score events. Same schema as daily but partitioned by hour. |
| `tracking_hourly.scoreeventforlogin` | Hourly login score events |
| `tracking_hourly.registrationattemptevent` | Hourly registration attempts |

**Note:** The `params` map may have different keys in hourly vs daily tables. Use `element_at(params, 'key')` instead of `params['key']` to avoid "Key not present in map" errors.

### Other Tracking Events (Daily)
| `tracking.securitychallengeevent` | All security challenges (captcha, RTS, phone, EPC, 2FA) |
| `tracking.pageviewevent` | Page views (lighter than user request event) |
| `tracking.userrequestevent` | All user requests (member + guest) |
| `tracking.userrequestdenialevent` | Request denial events with block filter rules |
| `tracking.scrapingscoreevent` | Scraping scorer decisions |
| `tracking.phonescoreevent` | Phone verification scoring |
| `tracking.passwordchangeevent` | Password changes |
| `tracking.passwordresetscoreevent` | Password reset score events |
| `tracking.memberaccountchangeevent` | Name/email changes |
| `tracking.memberhandlechangeevent` | Handle changes |
| `tracking.messagedeliveryevent` | Messages (SMS, email) delivered |
| `tracking.idverificationv2event` | Identity verification events |
| `tracking.followevent` | Follow events |
| `tracking.urimetadataevent` | URI metadata with hashed URLs |
| `tracking.ArkoseLabsRealTimeLoggingEvent` | Arkose bot detection |
| `tracking.VendorBotDetectionEvent` | Vendor bot detection (Shape/Human Security) |
| `tracking.emailbounceevent` | Email bounce events |
| `tracking.TwoStepOptinEvent` | 2FA opt-in events |
| `tracking.UserAccountRestrictionEvent` | Account restriction events |
| `tracking.FuseCounterActionEvent` | Counter-based actions |
| `tracking.contactsuploadevent` | Contacts upload / ABI |

### Columnar Variants (for JOINs on submissionid)
| Table | Purpose |
|-------|---------|
| `tracking_column.registrationEvent` | Columnar registration events |
| `tracking_column.scoreEvent` | Columnar score events |
| `tracking_column.loginevent` | Columnar login events |
| `tracking_column.securitychallengeevent` | Columnar challenge events |
| `tracking_column.userrequestevent` | Columnar user requests |
| `tracking_column.InvitationClickEvent` | Columnar invitation clicks |

### Streaming
| Table | Purpose |
|-------|---------|
| `kafka_streaming.scrapingscoreevent` | Real-time scraping events |
| `kafka_streaming.scoreevent` | Real-time score events |

### Member & Profile Data
| Table | Purpose |
|-------|---------|
| `prod_foundation_tables.dim_member_all` | Full member profile dimensions |
| `prod_foundation_tables.dim_member_trust_restrictions` | Trust restriction history |
| `data_derived.member_restrictions` | Current restriction info |
| `u_metrics.member_handles_union` | Member emails/handles |
| `prod_identity.profile` | Profile data |
| `entity_handles_mp.member_emails` | Member emails |

### Abuse & Fraud Datasets
| Table | Purpose |
|-------|---------|
| `u_metrics.fake_account_union` | Known fake accounts |
| `u_metrics.ato_volume_union` | ATO event volumes |
| `u_metrics.abuse_damage_ato_union` | ATO damage metrics |
| `u_metrics.dim_gco_case_osc` | Self-reports (account compromise, etc.) |
| `u_metrics.user_flagging_v3_union` | Community flagging data |
| `u_metrics.scraping_member_union` | Member scraping metrics |
| `u_metrics.scraping_funnel_union` | Scraping funnel with treeid |
| `u_metrics.registration_v2_union` | Unified registration table |
| `u_metrics.harm_union` | Harm/damage metrics |
| `u_far.irasta_results` | ASTA job results |
| `data_derived.securitylabels_fakeaccounts` | Fake account labels |
| `data_derived.securitylabels_guestscrapinglabelssnapshot` | Guest scraping labels |

### Security Features & Aggregates
| Table | Purpose |
|-------|---------|
| `data_derived.securityreputationsystems_registration` | Registration reputation |
| `data_derived.GeoReputation_IPReputation` | IP reputation data |
| `u_secaggs.ipDerivedFeatures` | IP-derived features |
| `u_secaggs.joinIPFeatures_latest` | Join IP features |
| `u_secaggs.profileFeatures_latest` | Profile features (positions, education, skills) |
| `u_secaggs.emailHandleFeatures` | Email handle features |
| `u_secaggs.phoneinfo` | Phone info |
| `u_secaggs.scrapingFeatures_latest` | Scraping features |
| `u_secaggs.invitation_skew_features` | Invitation targeting skew |
| `data_derived.member_membernumdaysactive` | Member activity (days active) |

### Device Fingerprinting
| Table | Purpose |
|-------|---------|
| `TRACKING.AntiAbuseJavaScriptDeviceFeaturesEvent` | JS device fingerprint features |
| `TRACKING.AntiAbuseJavaScriptDeviceFeaturesDFPWebEvent` | DFP web features |
| `TRACKING.AntiAbuseJavaScriptDeviceFeaturesDFPAndroidEvent` | DFP Android features |
| `TRACKING.HumanSecurityBotDefenderEvent` | Human Security bot defender |

### Behavioral Features
| Table | Purpose |
|-------|---------|
| `antiabusefeatures_member.m2mblockfeatures` | Member-to-member blocks |
| `antiabusefeatures_session.sessionprofilenameeditfeatures` | Profile name edits in session |
| `antiabusefeatures_session.sessionmessagessent` | Messages sent in session |
| `data_derived.InvitationHistory` | Invitation history |
| `data_derived.pageviews_member_aggregate_daily` | Daily pageview aggregates |
| `prod_conns.connections` | Connection graph (for fanout) |
| `prod_custservice.cs_audit_log_entries` | CS audit logs — full account behavioral timeline: logins, profile changes, password resets, restrictions, challenges, email/phone changes. No datepartition — filter by `event_time` (epoch ms). Key UDFs: `ip_country(ip_address)`, `ip_org_name(ip_address)`. Use for sampling 20-50 accounts to characterize cohort behavior. |

### Other
| Table | Purpose |
|-------|---------|
| `u_metrics.weekly_active_uniques_union` | WAU data |
| `prod_foundation_tables.dim_sales_navigator_seats` | SN seat data |
| `u_metrics.lss_dailydash_seats_union` | SN daily seats (paid/free) |
| `u_tdsato.pwi_cohorts_*` | Leaked password cohorts |
| `data_derived_column.lixexperimentassignmentdata_daily` | LIX experiment assignments |

## Common UDFs

### IP Functions
```sql
ip2str(ipasbytes)                    -- Convert IP bytes to string
ip_org_name(ip_string)               -- Get IP organization name
ip_country(ip_string)                -- Get IP country code (3-letter)
```

### Anti-Abuse UDFs
```sql
-- Distribution score (detect coordinated bot activity)
ADD JAR ivy://com.linkedin.transport-udfs-antiabuse-scores:transport-udfs-antiabuse-scores:0.0.9?classifier=hive;
CREATE TEMPORARY FUNCTION distribution_score AS 'com.linkedin.stdudfs.antiabuse.hive.DistributionScore';
-- Usage: distribution_score(array_agg(cnt order by minutes)) / 10000.0

-- Automation timing score (detect bot-like request timing)
automation_timing_score(array_agg(header__time)) / 10000.0
```

### Date Functions
```sql
daysAgo(N)                           -- Relative date (N days ago)
from_unixtime(ts / 1000)             -- Convert epoch ms to timestamp
date_format(..., '%Y-%m-%d-%H')      -- Format to partition-like string
date_trunc('minute', timestamp)      -- Truncate to minute
```

### Common Patterns
```sql
to_base64(header.treeid)             -- Convert treeid for joins
element_at(params, 'key')            -- Extract from params map
element_at(counterinfo, 'key')       -- Extract from counter map
try(params['key'])                   -- Safe param extraction (columnar)
contains(activatedrules, 'rule')     -- Check if rule activated
array_join(array_col, ', ')          -- Join array to string
split(urn, ':')[4]                   -- Extract member ID from URN
```

## Scorer Types

| Scorer Type | Purpose |
|-------------|---------|
| `SCORER_LOGIN` | Login scoring |
| `SCORER_REGISTRATION` | Registration scoring |
| `SCORER_MEMBER_REQUEST` | Invitation/connection scoring |
| `SCORER_CONTENT_CLASSIFICATION` | Content abuse scoring |

## im_playbooks Python Library

The `im_playbooks` repo (`/Users/styang/Documents/im_playbooks/`) provides reusable Python modules.

### Predefined Login Filters (`loginscore.py`)
```python
LOGIN_SCORER = ["scorerType= 'SCORER_LOGIN'", "scorerStage = 'CURRENT'"]
PASSWORD_PASS = ["try(params['password_result']) = 'PASS'"]
PASSWORD_PASS_NO_CAPTCHA = ["try(params['password_result']) = 'PASS'", "try(params['challenge_type']) = 'No Challenge'"]
```

### Login Counters (18 available)
`LOGIN_SUCCESSES_BY_MEMBER_5_MINUTE`, `LOGIN_SUCCESSES_BY_IP_24_HOUR`, `LOGIN_SUCCESSES_BY_BCOOKIE_24_HOUR`, `LOGIN_ATTEMPTS_BY_MEMBER_24_HOUR`, `LOGIN_ATTEMPTS_BY_IP_24_HOUR`, etc.

### Predefined Registration Filters (`regscore.py`)
```python
ALL_ATTEMPTS_FILTERS = ["scorerstage = 'CURRENT'", "scorertype = 'SCORER_REGISTRATION'"]
COLD_VALID_ATTEMPTS_FILTERS = ALL_ATTEMPTS_FILTERS + ["try(params['reg_input_data_validation']) = 'VALID'", "try(params['registration_type']) = 'COLD'"]
```

### Registration Counters (40+, by ASN/IP/bcookie/CC/HC)
`REGISTRATION_VALID_COLD_BY_SORTED_COOKIE_NAMES_24_HOUR`, `REGISTRATION_INVALID_COLD_BY_IP_24_HOUR`, etc.

### Challenge Type Mapping (`challenge.py`)
- `Captcha Challenge` → `CAPTCHA_CHALLENGE`, `NATIVE_CAPTCHA_CHALLENGE`
- `Email Pin Challenge` → `EMAIL_PIN_CHALLENGE`
- `Phone Challenge` → `PHONE_CHALLENGE`
- `Two Step Verification Challenge` → `TWO_STEP_VERIFICATION`, `TWO_STEP_VERIFICATION_AUTHENTICATOR_APP`, `TWO_STEP_VERIFICATION_BACKUP_CODE`

### Alert Detection Utilities (`alert_utils.py`)
- `compute_iqr_alert()` — IQR-based anomaly detection
- `compute_pct_above_rolling_avg()` — % above rolling average
- `compute_steady_increase_alert()` — Steady N-period increase
- `compute_period_over_period_increase_alert()` — WoW comparison

### Investigation Tools
- **InFinder**: `https://infinder.prod.linkedin.com/member-details?query_type=mid_details&start_date={DATE}&end_date={DATE}&mid={MIDS}`
- **Inspector/CSTool**: `https://cstool.www.linkedin.com/trust-tool/member/{MID}`

## DAVI Widgets Reference (run via `davi-runner` skill)

| Widget | Use Case | Skills |
|--------|----------|--------|
| `SevCalculatorWidget` | Automated cohort SEV assessment (DIHE + scraping WoW) | sev-assessment, account-takeover, fake-account-research, scraping |
| `DiheWidget` | DIHE analysis by account type (`fake` or `ato`) | account-takeover, fake-account-research |
| `IPActivityWidget` | IP/search pivot from MIDs or IPs | account-takeover, login-analysis, scraping |
| `CaptainScrapingWidget` | Per-member scraping patterns (InVizor) | scraping-investigation |
| `SurfaceVisualizationWidget` | Registration traffic with NL filtering | fake-account-research, suspicious-registrations |
| `KeywordsAnalysisWidget` | Find members searching specific keywords | messaging-abuse, scraping-investigation |
| `SearchTermRankingWidget` | Search term ranking by MIDs | messaging-abuse, scraping-investigation |
| `MagicPlotWidget` | Auto-detect and plot any DataFrame | general utility |

## Token-Efficient Query Patterns

Always prefer aggregated queries over raw SELECT *:

```sql
-- GOOD: Aggregated, grouped, limited
SELECT datepartition, loginresult, count(*) as c, count(distinct header.memberid) as mids
FROM tracking.loginevent
WHERE datepartition = '{DATE}-00'
GROUP BY 1, 2 ORDER BY c DESC LIMIT 20

-- BAD: Raw rows, no aggregation
SELECT * FROM tracking.loginevent WHERE datepartition = '{DATE}-00' LIMIT 1000
```

When building investigation queries:
1. `DESCRIBE {table}` first to check schema
2. Start with COUNT/GROUP BY to understand data shape
3. Only drill into raw rows after aggregation reveals the pattern
4. Use `approx_percentile()` instead of scanning for distributions
5. Use `count_if()` for conditional counting in a single pass
