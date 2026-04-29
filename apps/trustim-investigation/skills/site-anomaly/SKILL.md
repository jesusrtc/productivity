---
name: site-anomaly
description: >-
  Investigate site-wide anomalies using Trino queries. Covers QPS analysis, site speed metrics,
  traffic pattern anomalies, and IPv6 block analysis.
  Use when oncall for unexpected traffic spikes or site-wide metric changes.
allowed-tools: Bash
---

# Site Anomaly Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'trustim';`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking.userrequestdenialevent` | Denial events for block analysis |
| `tracking_column.userrequestevent` | User request events for QPS |
| `tracking.sitespeedevent` | Site speed/performance events |
| `tracking.scrapingscoreevent` | Scraping score for traffic analysis |

## Investigation Queries

The SQL for all queries below lives in the **`site-traffic`** action skill. Invoke that skill and use the named query listed for each step.

### 1. QPS by Hour
**Action:** `site-traffic` → *QPS by Hour*
- Params: `{DATE}` — the target date
- Use to measure hourly traffic and identify spikes or off-hours bot waves

### 2. IPv6 Block Rule Impact
**Action:** `site-traffic` → *IPv6 Block Rule Impact*
- Params: `{IPV6_RULE_NAME}` — the IPv6 block filter rule name
- Use to track daily denial counts for IPv6 block rules; check for FPR concerns

### 3. Top Denied IP Organizations
**Action:** `site-traffic` → *Top Denied IP Organizations*
- Params: `{DATE}` — the target date
- Use to identify the top hosting providers or ISPs generating blocked traffic

### 4. Site Speed Anomaly
**Action:** `site-traffic` → *Site Speed Anomaly*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to check P50/P90/P99 page load time degradation over a date range

### 5. Non-LinkedIn Referrer Traffic
**Action:** `site-traffic` → *Non-LinkedIn Referrer Traffic*
- Params: `{DATE}` — the target date
- Use to detect traffic from suspicious external referrers (phishing sites, redirect abuse)

## Tips

- Use `daysAgo(N)` for relative date filtering
- QPS spikes may indicate scraping attacks or bot waves
- IPv6 rules often have higher false-positive rates
- Site speed degradation can indicate abuse-related load
- Cross-reference with scraping scorer events for correlation
