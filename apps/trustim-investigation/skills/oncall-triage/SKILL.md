---
name: oncall-triage
description: >-
  General oncall triage queries for TrustIM. Covers member lookups, restriction checks,
  appeals monitoring, incident metrics (TTD/TTR), and common diagnostic queries.
  Use as a starting point for any oncall investigation.
allowed-tools: Bash
---

# Oncall Triage

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Common headless accounts:**
```sql
SET SESSION li_authorization_user = 'trustim';   -- general trust
SET SESSION li_authorization_user = 'ir2ato';    -- ATO investigations
SET SESSION li_authorization_user = 'ir2fake';   -- fake account investigations
SET SESSION li_authorization_user = 'ir2scraping'; -- scraping investigations
SET SESSION li_authorization_user = 'tdsfake';   -- TDS fake
SET SESSION li_authorization_user = 'tdsfraud';  -- TDS fraud
SET SESSION li_authorization_user = 'jobstrust'; -- jobs trust
SET SESSION li_authorization_user = 'login';     -- login investigations
SET SESSION li_authorization_user = 'register';  -- registration investigations
SET SESSION li_authorization_user = 'far';       -- FA research
SET SESSION li_authorization_user = 'scrapeds';  -- scraping DS
SET SESSION li_authorization_user = 'tdssample'; -- TDS sample
```

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `u_metrics.member_handles_union` | Member emails, handles |
| `prod_foundation_tables.dim_member_trust_restrictions` | Restriction status and history |
| `data_derived.member_restrictions` | Current restriction info |
| `u_metrics.fake_account_union` | Known fake accounts |
| `tracking.scoreevent` | Score events across all scorer types |
| `information_schema.tables` | Schema exploration |

## Investigation Queries

The SQL for all queries below lives in the **`member-lookup`** action skill. Invoke that skill and use the named query listed for each step.

### 1. Member Lookup
**Action:** `member-lookup` → *Member Handles Lookup*
- Params: `{MEMBER_ID}` — the member ID
- Use to retrieve email handles and basic info for a known member

### 2. Restriction Status Check
**Action:** `member-lookup` → *Restriction Status Check*
- Params: `{MEMBER_ID}` — the member ID
- Use to check the full restriction history for a single member

### 3. Appeals Monitoring
**Action:** `member-lookup` → *Appeals Monitoring*
- Params: `{START_DATE}` — start of the date range
- Use to track daily appeal volume and IMIR-related appeals

### 4. Incident Metrics - TTD and TTR
**Action:** `member-lookup` → *Incident Metrics TTD and TTR*
- Params: `{FY}` — fiscal year (e.g., `FY2026`)
- Use to calculate average time to detect and time to resolve for completed incidents

### 5. Explore Available Tables in a Schema
**Action:** `member-lookup` → *Explore Available Tables in a Schema*
- Params: `{USERNAME}` — schema username without the `u_` prefix
- Use to list all tables in a user schema when exploring available data

### 6. Copy Table Between Schemas
**Action:** `member-lookup` → *Copy Table Between Schemas*
- Params: `{TARGET_SCHEMA}`, `{TABLE_NAME}`, `{SOURCE_SCHEMA}`
- Use to copy a table from one headless account schema to another for sharing

### 7. Bulk Restriction Check
**Action:** `member-lookup` → *Bulk Restriction Check*
- Params: `{SCHEMA}` — headless schema; `{MID_TABLE}` — table of member IDs to check
- Use to check restriction status for a set of members at once

### 8. WAU Impact Calculation
**Action:** `member-lookup` → *WAU Impact Calculation*
- Params: `{DATE}` — reference date for WAU baseline
- Use to estimate percentage of Weekly Active Users affected by a restriction action

### 9. Self-Report Lookup (Account Compromise)
**Action:** `member-lookup` → *Self-Report Lookup*
- Params: `{MEMBER_ID}` — the member ID
- Use to check if a member has filed a TS-RHA account compromise self-report

### 10. Member Profile Enrichment
**Action:** `member-lookup` → *Member Profile Enrichment*
- Params: `{MEMBER_ID}` — the member ID
- Use to retrieve full profile attributes (country, industry, connections, join IP, email, restriction status)

### 11. User Flagging Check
**Action:** `member-lookup` → *User Flagging Check*
- Params: `{MEMBER_ID}` — the member ID
- Use to check if a member has been community-flagged for fake identity or spam

## Tips

- Start every investigation by identifying the right headless account
- Use `information_schema.tables` to explore available tables in any schema
- `daysAgo(N)` is a convenience function for relative date filtering
- Always check `is_current = true` for active restrictions
- For cross-schema data sharing, use `CREATE TABLE u_target.name AS SELECT * FROM u_source.name`
- Key scorer types: `SCORER_LOGIN`, `SCORER_REGISTRATION`, `SCORER_MEMBER_REQUEST`, `SCORER_CONTENT_CLASSIFICATION`
- Self-reports: `u_metrics.dim_gco_case_osc` with `ask_path = 'TS-RHA'` for account compromise
- Member profile: `prod_foundation_tables.dim_member_all` is the most comprehensive member dimension table
- User flagging: `u_metrics.user_flagging_v3_union` for community-reported flags

## Related Repos & Tools (from MCP discovery)

| Repo | Purpose |
|------|---------|
| `account-takeover-ai-agent-skills` | ATO investigation agent with `/investigate-member` and `/reporting-metrics` skills |
| `account-integrity-investigation` | IMIR incident response workflows for account integrity abuse |
| `investigations-workflows` | Cipher Crew investigation workflow library |
| `trust-investigation-web` | Trust investigation web frontend (Trust Foundations - Decisioning System) |
| `trust-rules-catalog` | Trust rules catalog backend (Trust Foundations) |
| `account-abuse-holistic-detection` | Holistic account abuse detection (Account Abuse AI) |
| `trust-account-agents` | Account abuse infrastructure agents |
| `investigation-agents` | Cipher Crew investigation agents |
| `unified-trust-features-lib` | Trust-wide Frame feature inventory (278+ features from antiabusefeaturematrix Venice store) |

## im_playbooks Reference

The `im_playbooks` repo (`/Users/styang/Documents/im_playbooks/`) contains 112 notebooks and a Python library for investigations.

### Alert Detection Utilities
Import from `com.linkedin.airpnb.lib.alert_utils`:
- `compute_iqr_alert()` — IQR-based anomaly detection
- `compute_pct_above_rolling_avg()` — % above rolling average
- `compute_steady_increase_alert()` — Steady N-period increase
- `compute_period_over_period_increase_alert()` — WoW / period-over-period

### Abuse Modules (com.linkedin.airpnb.abuse)
- `loginscore.py` — Login scorer filters, counters (18 login counters), params (30+ login params)
- `regscore.py` — Registration scorer filters, counters (40+ reg counters by ASN/IP/bcookie/CC/HC)
- `challenge.py` — Challenge solve rate calculation (`calc_challenge_solve_rate()`)
- `telesign.py` — Phone verification / telesign analysis
- `qps.py` / `guestqps.py` — QPS analysis

### Account Modules (com.linkedin.airpnb.account)
- `registration.py` — Registration event analysis
- `profile.py` — Profile data enrichment
- `session.py` — Session analysis

### Alerting Notebooks by Category
| Category | Path | Key Notebooks |
|----------|------|---------------|
| ATO | `alerting/ato/` | `alert_ato_umi.ipynb`, `alert_ato_rha_reports.ipynb`, `pwr_with_only_epc_alert.ipynb` |
| Fake Accounts | `alerting/fakeaccounts/` | `alert_FA_UMI.ipynb`, `alert_FA_DIHE.ipynb`, `alert_FA_memberReports.ipynb`, `registration_no_captcha.ipynb`, `Automation_Registration_Alert.ipynb` |
| IRSF | `alerting/irsf/` | `alert_telesign_cost.ipynb` |
| Jobs | `alerting/jobs/` | `alert_Jobs_DIHE.ipynb` |
| Dynamic Clustering | `alerting/dynamicclustering/` | `login_dynamicclustering_grouping.ipynb`, `password_reset_dynamicclustering_grouping.ipynb` |
| Reporting | `reporting/` | `Guest Scraping FPR Calculation*.ipynb`, `GhostLockLoginEvents.ipynb`, `device_fingerprint_coverage.ipynb` |

### Key Investigation Tools
- **InFinder**: `https://infinder.prod.linkedin.com/member-details?query_type=mid_details&start_date={DATE}&end_date={DATE}&mid={MIDS}`
- **Inspector/CSTool**: `https://cstool.www.linkedin.com/trust-tool/member/{MID}`
- **Iris Alerts**: Alerts created via `irisclient.IrisClient` with app=`liairp`
- **Darwin Notebooks**: `https://darwin.prod.linkedin.com/apps/publish/{RESOURCE_ID}`

## Key Oncall Resources
- ATO Self Reports form: https://www.linkedin.com/help/linkedin/ask/ts-rha (TS-RHA)
- Account Experience oncall docs: `account-experience-docs` repo (`docs/oncall-docs/`)
- Fake Account Profile Appeal: `appeals-service` repo — members restricted for FA can appeal via IDV
- Account Abuse AI oncall plugin: `li-productivity-agents/linkedin-plugins/specialized/account-abuse-oncall/`
- Investigation threshold proposal: https://docs.google.com/document/d/1KwyJK-uhVguKOGD22tKirBezLle-Srn2vbXW_WpRin4/
