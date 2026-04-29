---
name: suspicious-registrations
description: >-
  Investigate suspicious member registrations using Trino queries. Covers registration attacks,
  email/IP pattern analysis, reg score discrepancies, cookie signal detection, and coordinated
  signup detection. Use when oncall for registration spikes or fake account waves.
allowed-tools: Bash
---

# Suspicious Registrations Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. **Never mix column styles.** `tracking.registrationevent` uses dot notation (`email`, `header.memberid`, `ip2str(requestheader.ipasbytes)`). `tracking_column.registrationEvent` uses double-underscore (`header__memberid`, `requestheader__ip`). If unsure, run `DESCRIBE {table_name}` first. See `common-reference` for the full mapping.
2. Run `DESCRIBE {table_name}` to check current schema before constructing queries
3. Build queries based on the live schema, columns may have changed
4. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
5. Always filter on `datepartition` and use `LIMIT`
6. Never return raw PII, aggregate by IP org, email domain, country, etc. instead of individual values
7. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool to run these queries on the **holdem** server.

**Always include this preamble:**
```sql
SET SESSION li_authorization_user = 'trustim';
```

**Partition formats:**
- Daily tables: `YYYY-MM-DD-00` (e.g., `2026-03-11-00`)
- Hourly tables: `YYYY-MM-DD-HH` (e.g., `2026-04-02-14`). Hourly tables retain ~2-3 days of data.

## Common Gotchas

These caused errors during real investigations and should be avoided:

1. **`requestheader.ip` is null in most tables.** Use `ip2str(requestheader.ipasbytes)` instead. The `requestheader__ip` column in columnar tables is also frequently null.

2. **`params['key']` throws "Key not present in map" if the key doesn't exist in every row.** Use `element_at(params, 'key')` instead, which returns null for missing keys. This is especially important for `email_domain`, `asn`, and other optional params fields.

3. **The `params` map has different keys in the hourly vs daily tables.** For example, `params['asn']` exists in `tracking_hourly.scoreeventforregistration` but may not exist in `tracking.scoreeventforregistration`. Always use `element_at()` and test on a sample before running at scale.

4. **The Ultrascrapper pipeline in `u_metrics.scraping_member_labels_union` does not cover accounts under ~30 days old.** Zero Ultrascrapper labels for recently created accounts is inconclusive. Always run a control group (baseline registrations from multiple countries on a non-spike day) before drawing conclusions.

5. **QCS throttling drops requests at L1 before they reach the scorer.** When QCS is active, recommendations about challenge types (Captcha, Phone) only apply to requests that pass L1. Separately recommend per-IP drop priorities for L1.

## Key Tables

| Table | Purpose | Partition Format |
|-------|---------|-----------------|
| `tracking.registrationevent` | Successful registrations (email, name, method, mobile header) | `YYYY-MM-DD-00` |
| `tracking.registrationattemptevent` | All registration attempts (includes failures) | `YYYY-MM-DD-00` |
| `tracking.scoreeventforregistration` | **Preferred daily** for registration scoring. Pre-filtered to SCORER_REGISTRATION, leaner and faster | `YYYY-MM-DD-00` |
| `tracking_hourly.scoreeventforregistration` | **Preferred hourly** for intra-day analysis during active spikes. Same schema as daily but partitioned by hour | `YYYY-MM-DD-HH` (e.g., `2026-04-02-14`) |
| `tracking_column.registrationEvent` | Columnar registration events (for joins on submissionid) | `YYYY-MM-DD-00` |
| `tracking_column.scoreEvent` | Columnar score events (all scorer types, use only when you need JOINs on submissionid with other columnar tables) | `YYYY-MM-DD-00` |
| `data_derived.member_restrictions` | Member restriction status | `YYYY-MM-DD-00` |
| `data_derived.securityreputationsystems_registration` | Registration reputation system data | `YYYY-MM-DD-00` |
| `tracking.phonescoreevent` | Phone verification scoring with telesign data | `YYYY-MM-DD-00` |
| `u_metrics.scraping_member_labels_union` | Scraping member labels (Ultrascrapper, CDT, HUMAN, Browserless, etc.). Note: pipeline has ~3-4 day lag and does not effectively cover accounts under ~30 days old | `YYYY-MM-DD-00` |

## IP Enrichment UDFs

These UDFs work on any table with `requestheader.ipasbytes`:

| UDF | Usage | Returns |
|-----|-------|---------|
| `ip2str(requestheader.ipasbytes)` | Convert binary IP to string | IPv4 or IPv6 string |
| `ip_country(ip2str(requestheader.ipasbytes))` | Get country code from IP | 3-letter country code (e.g., `ita`, `usa`) |
| `ip_org_name(ip2str(requestheader.ipasbytes))` | Get organization/ISP name from IP | Org name string |

For subnet analysis, use `SPLIT_PART` on the IPv4 string:
```sql
-- /24 subnet
CONCAT(SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 1), '.',
       SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 2), '.',
       SPLIT_PART(ip2str(requestheader.ipasbytes), '.', 3), '.0/24')
```

## Investigation Queries

The SQL for all queries below lives in the **`registration-events`** action skill. Invoke that skill and use the named query listed for each step.

### 1. High-Volume Email Domain Detection
**Action:** `registration-events` → *High-Volume Email Domain Detection*
- Params: `{DATE}` — the target date
- Use as the first query for any registration spike to find suspicious domain concentration

### 2. Suspicious Email Username Patterns
**Action:** `registration-events` → *Suspicious Email Username Patterns*
- Params: `{DATE}` — the target date
- Use to detect bot-generated email addresses (numeric-heavy, consonant-only, disposable TLDs)

### 3. Suspicious Name Patterns
**Action:** `registration-events` → *Suspicious Name Patterns*
- Params: `{DATE}` — the target date
- Use to detect bot-like names (first = last, single char, digit sequences)

### 4. IP-Based Coordinated Registration Attack
**Action:** `registration-events` → *IP-Based Coordinated Registration Attack*
- Params: `{DATE}` — the target date
- Use to identify IPs driving high registration volumes with low attribute diversity

### 5. Registration Score Discrepancy
**Action:** `registration-events` → *Registration Score Discrepancy*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to find model/rule misalignment where model predicted "No Challenge" but rules didn't match

### 6. Cookie Signal Detection (Fake Romance Pattern)
**Action:** `registration-events` → *Cookie Signal Detection — Adobe/Fake Romance Pattern*
- Params: `{DATE}` — the target date
- Use to detect the Adobe tracking cookie (AMCVS/AMCV) fake romance signal

### 7. Registration Counter Signals
**Action:** `registration-events` → *Registration Counter Signals*
- Params: `{DATE}` — the target date
- Use to check counter distributions (by cookie name combo) for coordinated attack patterns

### 8. Country-Level Registration Clustering
**Action:** `registration-events` → *Country-Level Registration Clustering*
- Params: `{START_HOUR}`, `{END_HOUR}` — hourly partition range (e.g., `2026-04-02-04` to `2026-04-02-19`)
- Use as first query during any QPS spike to identify which country is driving the volume
- Returns total attempts, unique IPs, and attempts/IP per country; attempts/IP > 3x other countries = anomalous

### 9. Per-IP Threshold Coverage Analysis
**Action:** `registration-events` → *Per-IP Threshold Coverage Analysis*
- Params: `{START_HOUR}`, `{END_HOUR}`, optional `{COUNTRY}` filter
- Quantifies what percentage of traffic each per-IP rate threshold would catch
- Use to determine where to set L1 drop thresholds during QCS pressure
- Returns IP count, attempt count, and No Challenge count per bucket (1-2, 3-4, 5-9, 10-19, 20-49, 50+)

### 10. ASN/Organization Clustering
**Action:** `registration-events` → *ASN/Organization Clustering*
- Params: `{START_HOUR}`, `{END_HOUR}`
- Groups by `ip_org_name()` and `ip_country()` to find concentrated organizations
- High attempts/IP from a single org = VPS abuse, corporate proxy, or residential proxy botnet

### 11. Subnet Concentration (/24)
**Action:** `registration-events` → *Subnet Concentration*
- Params: `{START_HOUR}`, `{END_HOUR}`
- Groups IPv4 traffic by /24 subnet with attempts/IP ratio
- Subnets with >30 attempts/IP and few unique IPs = datacenter or coordinated farm

### 12. Browser Fingerprint Multiplexing
**Action:** `registration-events` → *Browser Fingerprint Multiplexing*
- Params: `{START_HOUR}`, `{END_HOUR}`, optional `{COUNTRY}` filter
- Counts unique browser fingerprints per IP; >5 per hour = consistent with residential proxy rotation
- Normal users have 1-2 browsers per IP

### 13. User Agent Uniformity Detection
**Action:** `registration-events` → *User Agent Uniformity Detection*
- Params: `{START_HOUR}`, `{END_HOUR}`, `{COUNTRY}`
- Returns top user agents with counts for a country's traffic
- Organic traffic follows a power-law distribution; botnet traffic shows uniform distribution (std dev < 50 across top 15 UAs)

### 14. Model Score Distribution / No Challenge Gap
**Action:** `registration-events` → *Model Score No Challenge Gap*
- Params: `{START_HOUR}`, `{END_HOUR}`
- Buckets model scores for registrations that received No Challenge
- Identifies high-risk registrations (score >= 0.8) bypassing challenges

### 15. Challenge Distribution Comparison
**Action:** `registration-events` → *Challenge Distribution Comparison*
- Params: Two sets of hourly ranges to compare (e.g., spike period vs post-throttle period)
- Shows challenge type breakdown per period to determine if QCS throttling targeted bot traffic or reduced all traffic equally

### 16. 30-Day Country Trend
**Action:** `registration-events` → *30-Day Country Trend*
- Params: `{START_DATE}`, `{END_DATE}`, list of countries
- Daily attempts and unique IPs per country from the daily `tracking.scoreeventforregistration` table
- Use to identify escalating patterns over time and compute baseline multiples

### 17. Completion Funnel (Attempts vs Completions)
**Action:** `registration-events` → *Completion Funnel*
- Params: `{DATE}`, optional `{COUNTRY}` filter
- Joins `tracking.registrationattemptevent` with `tracking.registrationevent` to compute attempt-to-completion rates
- Use to measure how many bot registrations actually complete

### 18. Ultrascrapper Cross-Reference
**Action:** `registration-events` → *Ultrascrapper Cross-Reference*
- Params: `{REG_DATES}` (registration date range), `{LABEL_DATE}` (scraping label partition)
- Joins completed registrations with `u_metrics.scraping_member_labels_union`
- IMPORTANT: Always run a control group (baseline registrations from a non-spike day, from multiple countries) alongside the target group. The Ultrascrapper pipeline does not effectively cover accounts under ~30 days old. An absence of labels is inconclusive without the control group comparison.

## Playbook Investigation Flows (from im_playbooks)

### Fake Accounts at Registration Triage (Fake Accounts at Registration Triage Playbook.ipynb)
1. Create triage MID table from alert or existing query
2. Fetch registration telemetry (IoCs: ip_org, useragent, canvas hash)
3. Calculate canvas hash + IoC combinations — group by to find clusters
4. Analyze restriction percentage by IoC combo
5. Explore registration timestamps — look for temporal clustering (automated bulk reg)
6. Analyze email domains and name patterns
7. Check invitation sending behavior post-registration
8. Analyze recipient targeting patterns
9. **Decision**: Restriction rate >70% for canvas hash + ip_org combo + >50 accounts = attack signature
10. **Signals**: Bounced email (classification 1/10/40), same domain cluster + same IP org, invitation spike post-reg

### Registration No Captcha Triage (pb_registration_no_captcha.ipynb)
1. Identify registrations from yesterday with no captcha given
2. Compare to 7-day overlay baseline using IQR method
3. Analyze attribute increases: UA, IP org, country, email domain, registration method
4. Check canvas hash + IP org restriction rates
5. Check for bounced email registrations
6. Correlate with other challenge types being offered
7. **Decision**: High reg volume + no captcha + restriction rate >70% = attack bypassing defenses
8. **Threshold**: IQR method on captcha offering rates; sudden decrease = defense gap

### Registration QPS Triage (pb_regqps.ipynb)

**Two layers to investigate:** L1 (QCS throttling, drops requests before scoring) and the Scorer (assigns challenge types to requests that pass L1). When QCS is throttling, requests are dropped at L1 based on total QPS without per-IP or per-signal differentiation. Recommendations must specify which layer they target.

**L1 Analysis (when QCS throttling is active):**
1. Run *Country-Level Registration Clustering* (#8) on the hourly table to identify which country is driving the volume spike
2. Run *Per-IP Threshold Coverage Analysis* (#9) for the anomalous country to quantify what per-IP thresholds would drop what percentage of bot traffic
3. Run *Per-IP Threshold Coverage Analysis* (#9) globally (no country filter) to assess false positive risk at each threshold
4. Run *ASN/Organization Clustering* (#10) to identify VPS/cloud providers and concentrated ISPs
5. Determine L1 drop priority tiers: always drop VPS/cloud ASNs first, then high-per-IP-rate IPs, then signature-based combinations
6. A blanket per-IP threshold without additional signals (country, email domain, browser) risks dropping shared/CGNAT IPs

**Scorer Analysis (for requests that pass L1):**
1. Monitor COLD and WARM registration success/attempts QPS
2. Analyze attribute spikes: referer, UA, email domain, IP country, browser, OS
3. Extract attack signature (UA + email domain + IP country combo)
4. Check form fill time from browserID timestamp, <30 sec = bot
5. Run *Model Score No Challenge Gap* (#14) to find high-score registrations bypassing challenges
6. Run *Challenge Distribution Comparison* (#15) to check if challenges are being assigned differently during spike vs baseline
7. Run *User Agent Uniformity Detection* (#13) for the anomalous country; uniform distribution (std dev < 50) = emulator/device farm
8. Run *Browser Fingerprint Multiplexing* (#12) to detect residential proxy rotation (>5 browsers per IP per hour)
9. Analyze captcha solve rates by signature
10. Generate behavioral rules using counters

**Post-Registration Analysis:**
1. Run *Completion Funnel* (#17) to measure how many bot registrations actually complete
2. Run *Ultrascrapper Cross-Reference* (#18) with a control group to check for scraping activity
3. Run *30-Day Country Trend* (#16) to determine how long the attack has been escalating

**Decision:** Short fill time + specific UA/domain combo + spike = automated attack. L1 recommendations should specify per-IP drop thresholds with coverage percentages. Scorer recommendations should specify challenge type overrides.

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `SurfaceVisualizationWidget` | `SurfaceVisualizationWidget(start_date="2026-03-01", end_date="2026-03-14", prompt="top 10 countries hourly line chart")` | Registration traffic visualization with NL filtering — supports country, OS, device, org breakdowns; daily/hourly; line/bar/pie charts |

## UA IOC guardrail

- For UA-driven registration IOCs: check the phone builds spreadsheet release date vs investigation date. If recent, require convergent non-UA abuse signals before labeling abusive. See `sev-assessment` guardrail.

## Tips

- Replace `{DATE}` with the target date (e.g., `2026-03-11`)
- For hourly granularity, use `BETWEEN '{DATE}-05' AND '{DATE}-16'` format
- Join with `data_derived.member_restrictions` to check if accounts are already restricted
- Use `ip_org_name(ip2str(requestheader.ipasbytes))` to get IP organization names (dot notation for `tracking.*` tables)
- Use `ip_country(ip2str(requestheader.ipasbytes))` to get IP country codes (dot notation for `tracking.*` tables)
- For columnar tables (`tracking_column.*`), use `ip2str(requestheader__ipasbytes)` (double-underscore notation)
