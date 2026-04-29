---
name: rule-tuning
description: >-
  Analyze and tune trust/safety rules using Trino queries. Covers rule performance tracking,
  FPR/UMI calculations, distribution scoring, counter signal analysis, and drools exception
  monitoring. Use when tuning rules or assessing rule impact.
allowed-tools: Bash
---

# Rule Performance Tuning

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
| `tracking.scoreevent` / `tracking_column.scoreEvent` | Score events with activated rules |
| `u_metrics.fake_account_union` | FA ground truth for precision |
| `prod_foundation_tables.dim_member_trust_restrictions` | Restriction data for recall |
| `tracking_column.userrequestevent` | User request events for distribution scoring |
| `data_derived_column.lixexperimentassignmentdata_daily` | LIX experiment assignments |

## Investigation Queries

The SQL for all queries below lives in the **`rule-performance`** action skill. Invoke that skill and use the named query listed for each step.

### 1. Rule Trigger Volume (Daily)
**Action:** `rule-performance` → *Rule Trigger Volume (Daily)*
- Params: `{START_DATE}`, `{END_DATE}` — the date range; `{RULE_NAME}` — exact rule name; `{SCORER_TYPE}` — scorer type
- Use to track daily trigger counts and confirm rule deployment

### 2. FPR (False Positive Rate) Calculation
**Action:** `rule-performance` → *FPR (False Positive Rate) Calculation*
- Params: `{START_DATE}`, `{END_DATE}` — the date range; `{RULE_NAME}` — exact rule name
- Use to measure precision and FPR for a rule; target FPR < 5% for production rules

### 3. UMI (Unique Member Impact) Calculation
**Action:** `rule-performance` → *UMI (Unique Member Impact) Calculation*
- Params: `{START_DATE}`, `{END_DATE}` — the date range; `{SCORER_TYPE}` — scorer type
- Use to measure how many unique members are impacted by all defensive actions for a scorer

### 4. Distribution Score Analysis
**Action:** `rule-performance` → *Distribution Score Analysis*
- Params: `{DATE}` — the target date; `{TARGET_UA}` — user agent string to analyze
- Use to compute distribution score for a user agent; > 0.8 indicates bot-like concentrated traffic

### 5. Drools Exception Monitoring
**Action:** `rule-performance` → *Drools Exception Monitoring*
- Params: `{START_DATE}`, `{END_DATE}` — the date range; `{SCORER_TYPE}` — scorer type
- Use to monitor RuleSetType_GENERIC_exception rate; elevated rates = drools failing open

### 6. LIX Experiment Impact
**Action:** `rule-performance` → *LIX Experiment Impact*
- Params: `{EXPERIMENT_ID}` — the LIX experiment ID; `{DATE}` — the target date
- Use to verify experiment ramp and treatment/control split

## Laser-to-Quasar Migration

The Laser model has been deprecated and replaced by Quasar. Migration requires careful per-rule analysis due to varying correlation between the two models.

### Key Details
- Correlation between Laser and Quasar scores varies by rule: 0.033 to 0.64
- Model name must be hardcoded in Drools — new model ramps require re-review of all affected rules
- Quasar score ranges: 0.28–0.78 for captcha assignment; >0.2 = 99% precision for ATT rule

### Reference
- [IM Laser deprecation](https://docs.google.com/document/d/1Fx3wSwEQFfszfySHEN4n2RLb_Z24sFuji0Q5u_3Ebz8/edit)

## Fake Romance Registration Patterns

Known signals from fake romance registration campaigns useful for rule tuning.

### IP Organizations
- Verizon Business, T-Mobile USA, Campana Taro Co. Ltd., Hurricane Electric LLC, Amazon Data Services Nova

### Email Domains
- High restriction rate (~80%): bk.ru, inbox.ru, list.ru, rambler.ru, mail.ru
- Outlook regex pattern: `[letters]+[digits]@outlook.com`

### Browser Fingerprint Signals
- AMCVS cookie: `AMCVS_14215E3D5995C57C0A495C55%40AdobeOrg`
- AMCV cookie: `AMCV_14215E3D5995C57C0A495C55%40AdobeOrg`

### Restriction Rates by Pattern
| Pattern | Restriction Rate |
|---------|-----------------|
| .ru email domains | 80% |
| hotmail/outlook (general) | 60% |
| Outlook regex (`[letters]+[digits]@outlook.com`) | 49% |
| FR IP orgs | 42% |
| ATT Mobility | 10% |

## Tips

- FPR = 1 - Precision; target FPR < 5% for production rules
- Distribution score > 0.8 indicates concentrated (bot-like) activity
- Always compare rule performance across 7-30 day windows
- Use `contains(activatedrules, '{RULE_NAME}')` for exact rule matching
- Monitor drools exceptions — they indicate scorer infrastructure issues

## Playbook Rule Generation Pattern (from im_playbooks)

All QPS playbooks (login, registration, guest scraping) follow this rule generation workflow:

### Rule Generation Workflow
1. **Identify attack signature** — Cluster by HC + CC + UA + IP org + email domain
2. **Calculate recall** — (pattern traffic) / (total increased traffic)
3. **Calculate precision** — 1 - (overlay traffic matching pattern) / (current traffic matching pattern)
4. **Train decision tree** on positive (attack) vs negative (baseline) samples
5. **Extract rule conditions** from tree leaves with highest precision
6. **Generate counter-based rules** using Nebula counters (e.g., `REGISTRATION_VALID_COLD_BY_SORTED_COOKIE_NAMES_24_HOUR > threshold`)
7. **Deploy as IR rule** in drools with appropriate action (RESTRICT, DELAY, CHALLENGE)
8. **Monitor rule performance** — track trigger volume, FPR, UMI impact

### Alert Detection Methods (from alert_utils.py)
- **IQR Alert**: Flag if value > Q3 + 1.5*IQR (outlier detection)
- **Rolling Average**: Flag if value > rolling_avg * (1 + pct_threshold/100)
- **WoW Increase**: Flag if current week > previous week * (1 + pct_threshold/100)
- **Steady Increase**: Flag if N consecutive periods show > pct_threshold% increase
- **Fixed Value**: Flag if value > fixed_threshold * (1 + pct_threshold/100)

### Common Alert Thresholds
| Metric | Threshold | Method |
|--------|-----------|--------|
| ATO UMI | 20% WoW increase | Period-over-period |
| FA DIHE | > 55M or 20% WoW | Fixed value + WoW |
| Registration no-captcha | IQR outlier | IQR method |
| Login QPS | IQR outlier | IQR on challenge rates |
| Guest scraping | 15% above 9-week rolling avg | Rolling average |
