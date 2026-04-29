---
name: scraping-investigation
description: >-
  Investigate guest and member scraping using Trino queries. Covers scraping funnel analysis,
  block filter rules, denial events, IP/org research, and FPR checks.
  Use when oncall for scraping spikes or block filter tuning.
allowed-tools: Bash
---

# Scraping Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'ir2scraping';`

Other headless accounts: `scrapeds`, `trustim`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking.userrequestdenialevent` | Request denial events with block filter rules |
| `tracking.scrapingscoreevent` / `kafka_streaming.scrapingscoreevent` | Scraping scorer decisions |
| `u_metrics.scraping_member_union` | Aggregated scraping member data |
| `u_metrics.scraping_funnel_union` | Scraping funnel with treeid correlation |

## Investigation Queries

The SQL for queries 1–9 lives in the **`scraping-events`** action skill, and query 10 lives in the **`device-fingerprint`** action skill. Invoke those skills and use the named query listed for each step.

### 1. Block Filter Rule Volume
**Action:** `scraping-events` → *Block Filter Rule Volume*
- Params: `{RULE_NAME}` — the block filter rule name
- Use to track daily denial counts and confirm rule is firing after deployment

### 2. Denial Event Detail
**Action:** `scraping-events` → *Denial Event Detail*
- Params: `{RULE_NAME}` — the block filter rule name
- Use to inspect individual denial events (IP, path, referer, UA, cookies) for pattern analysis

### 3. Scraping Funnel Correlation
**Action:** `scraping-events` → *Scraping Funnel Correlation*
- Params: `{RULE_NAME}` — the block filter rule name
- Use to measure what fraction of denied traffic is actual scrapers (FPR check)

### 4. Scraping Score Event Analysis
**Action:** `scraping-events` → *Scraping Score Event Analysis*
- Params: `{DATE}` — the target date
- Use to analyze scorer decisions by cookie patterns

### 5. Member Scraping Profile Lookup
**Action:** `scraping-events` → *Member Scraping Profile Lookup*
- Params: `{MEMBER_IDS}` — comma-separated list of member IDs
- Use to check scraping classification and activity metrics for specific members

### 6. Guest Scraping FPR Check
**Action:** `scraping-events` → *Guest Scraping FPR Check*
- Params: `{DATE}` — the target date
- Use to verify false positive rate for scraping rules on guest (unauthenticated) traffic

### 7. Authwall Funnel Analysis
**Action:** `scraping-events` → *Authwall Funnel Analysis*
- Params: `{DATE}` — the target date
- Use to track how many scrapers are redirected to the authwall login/registration flow

### 8. Bot Model Classification
**Action:** `scraping-events` → *Bot Model Classification*
- Params: `{DATE}` — the target date
- Use to see bot model v2 classification results broken down by IP org

### 9. Scraping FPR Confusion Matrix
**Action:** `scraping-events` → *Scraping FPR Confusion Matrix*
- Params: `{DATE}` — the target date
- Use for full TP/FP/TN/FN precision and FPR calculation with security label ground truth

### 10. Device Fingerprint for Member Scraping
**Action:** `device-fingerprint` → *VM and Automation Detection via Score Events*
- Params: `{DATE}` — the target date; `{MEMBER_IDS}` — comma-separated list of member IDs
- Use to detect VMs and automation tools (SwiftShader in vendorAndRenderer = VM)

## Tips

- Guest scraping: `header.memberid = 0` (not logged in)
- Member scraping: `header.memberid > 0`
- Use `ip_org_name(ip2str(request.ipasbytes))` to identify scraping orgs
- Key scraping paths: `in/%` (profiles), `company/%`, `jobs/%`, `directory/%`
- Cookie analysis is critical — compare `scoringheader.cookienames` patterns
- Authwall funnel: scraping score -> sentinel redirect -> login/registration conversion
- Bot model v2 classification available via `CROSS JOIN UNNEST(modelresults)`
- FPR calculation requires `data_derived.securitylabels_guestscrapinglabelssnapshot` for ground truth
- VM detection: SwiftShader or VMware in WebGL vendorAndRenderer field
- `automation_timing_score()` UDF detects bot-like request timing patterns

## Logged-in Scraping Detection Pipeline

Uses Backend Call Detail Tracking (BE CDT) data for profile data egression outlier detection on logged-in members.

### Key Tables
| Table | Purpose |
|-------|---------|
| `service.voyager_api_identity_dash_log_event` | Dash + GraphQL profile data requests |
| `service.voyager_api_identity_log_event` | Pre-Dash profile data requests |

### Alert Thresholds

| Metric | Baseline | Alert Threshold |
|--------|----------|----------------|
| New account data egression | 200M | 25% WoW increase |
| 7-day FA lookback egression | 200M | 25% WoW increase |
| Pre-Dash requests | 4M | 25% WoW increase |
| Total data egression (Experience) | 13B | 1% WoW increase |
| Total data egression (Headline) | 31.5B | 1% WoW increase |
| Dash requests | 500M | 1% WoW increase |
| GraphQL requests | 2.5B | 1% WoW increase |
| Any single GraphQL query usage | varies | 100% WoW increase |

### Investigation Runbook
1. Check restriction/friction status for flagged accounts
2. Check subscription type (premium accounts may have legitimate high usage)
3. Check backstop gaps in existing defenses
4. Run daily offline URE (User Request Event) backstop
5. Run hourly URE counter for high-risk accounts (<1 week old + 0 connections)

### Limitations
- Client-side ProfileViewEvent misses automators (they skip the client)
- Scraping accounts for ~5% of total egression at steady state

### Reference
- [Scraping detection pipeline](https://docs.google.com/document/d/1Ktkd5ulObhmOW38aPRHON_QXghepI3ygeQSrnLE_Vrk/edit)

## Playbook Investigation Flow (from im_playbooks: pb_guestscraping.ipynb)

### Guest Scraping QPS Triage
1. Plot QPS overlay (current vs 7 days ago) using `kafka_streaming.scrapingscoreevent`
2. Analyze attribute increases: Cookie Combo (CC), Header Combo (HC), User Agent (UA)
3. Calculate recall & precision of attack pattern:
   - **Recall** = (pattern traffic) / (total increased traffic)
   - **Precision** = 1 - (overlay traffic) / (current traffic)
4. Check IP org distribution for the attack pattern
5. Analyze browserid patterns (null browserid = headless bot)
6. Check shape label (bot detection) via `data_derived.securitylabels_guestscrapinglabels_daily`
7. Monitor FunCaptcha solve rates — low solve rate = bots failing challenge
8. Generate defense rules via decision tree on positive/negative samples
9. Monitor IR rule performance after deployment
10. **Key Signals**: CC pattern missing AMCV = suspicious; HC standardization = bot; low FunCaptcha solve = automated
11. **Decision**: IP org + HC + UA clustering = coordinated attack → create block filter rule

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `CaptainScrapingWidget` | `CaptainScrapingWidget(memberid=59271, datepartition="2026-03-01-00")` | Per-member scraping pattern analysis (InVizor) — treeID/sourceURN timelines, scatter plot |
| `IPActivityWidget` | `IPActivityWidget(input_values=[MID1, MID2], period="30d")` | IP/search pivot — find IPs used by scraper MIDs, or MIDs behind suspicious IPs |
| `SearchTermRankingWidget` | `SearchTermRankingWidget(mids=[MID1, MID2], period="30d")` | Top search terms by frequency for suspected scraper MIDs |
| `KeywordsAnalysisWidget` | `KeywordsAnalysisWidget(keywords=["linkedin profile", "email list"], period="7d")` | Find members searching specific scraping-related keywords |
| `SevCalculatorWidget` | `SevCalculatorWidget(cohort_member_ids="SELECT mid FROM ...")` | Automated SEV assessment for scraping cohort (data egress WoW with charts) |
