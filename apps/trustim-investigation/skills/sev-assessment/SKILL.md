---
name: sev-assessment
description: >-
  Assess incident severity (SEV 1-4) for abuse incidents using the official SEV framework.
  Covers True North metrics (member reports, self-reports, prevalence), cohort-based harm metrics
  (DIHE, PVV, Telesign, scraping), SEV modifiers, merge rules, and a UA IOC guardrail: compare phone-builds
  spreadsheet release dates to the investigation date; be cautious on fresh releases unless other signals are abusive.
  Includes SQL templates for WoW T7D computation and references the DAVI SevCalculatorWidget for automated assessment.
allowed-tools: Bash
---

# SEV Assessment

## How to Use This Skill

Use this skill when you need to:
- Determine the SEV level for an abuse incident
- Compute WoW T7D changes for True North or cohort-based metrics
- Apply SEV modifiers (boost/demote) to a base SEV
- Decide whether to merge multiple SEVs

**Reference docs:**
- [SEV Levels for Abuse Incidents](https://docs.google.com/document/d/163DM1Wu09zrJBnpCNMLE0MO0z51DiureZBPHk_qyzJU/edit)
- [SEV Calculator RFC](https://docs.google.com/document/d/1KrGC9X9A7ipsHQwzEjWqn8GTbGDRwNYFBFtDvRitE4o/edit)
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'trustim';`

Other headless accounts: `ir2ato`, `ir2fake`, `ir2scraping`

**Partition format:** `YYYY-MM-DD-00`

## SEV Framework Overview

SEV assignment is based on three factors:
1. **Magnitude** — How much harm has occurred (% increase in metrics)
2. **Velocity** — How quickly it happened (days vs weeks/months)
3. **SEV Modifiers** — Factors that boost or demote severity

**Flow:**
1. Calculate WoW % change: `(Current T7D - Previous T7D) / Previous T7D`
2. Determine **Base SEV** from magnitude/velocity thresholds (Section 1 or 2 below)
3. Apply **Modifiers** (Section 3) to get **Final SEV**

**Threshold source of truth:** [SEV Levels for Abuse Incidents](https://docs.google.com/document/d/163DM1Wu09zrJBnpCNMLE0MO0z51DiureZBPHk_qyzJU/edit) — thresholds below are current as of March 2026. If in doubt, read the doc via `read_google_docs_document` (doc ID: `163DM1Wu09zrJBnpCNMLE0MO0z51DiureZBPHk_qyzJU`, tab: `t.7m8z6lvt81lf`).

## 1. True North Metrics (Table 1)

For Trust True North metrics, use the metric's own WoW change to determine SEV.

| Metric Bucket | Metric | SEV 1 | SEV 2 | SEV 3 | SEV 4 |
|---------------|--------|-------|-------|-------|-------|
| Prevalence @ Response | Prevalence @ Response (T28D) | >40% | >25% | >20% | >15% |
| Member self reports | ATO self reports (T7D) | >40% | >25% | >20% | >15% |
| Member reports | ATO member reports (T7D) | >40% | >25% | >20% | >15% |
| Member reports | FA member reports (T7D) | >35% | >20% | >15% | >10% |
| Member reports | Private Content Reports (T7D) | >35% | >20% | >15% | >10% |
| Member reports | Public Content Reports (T7D) | >35% | >20% | >15% | >10% |

### True North SQL Templates

**ATO Self Reports WoW:**
```sql
WITH daily AS (
  SELECT datepartition,
    COUNT(*) AS cases
  FROM u_metrics.gco_case_v2_union
  WHERE datepartition >= daysago(21)
    AND ask_path IN ('TS-RHA')
    AND category_name IN ('ATO -TnS-', 'Account Compromise - TnS')
  GROUP BY 1
),
t7d AS (
  SELECT datepartition,
    SUM(cases) OVER (ORDER BY datepartition ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS t7d_sum
  FROM daily
)
SELECT datepartition, t7d_sum,
  LAG(t7d_sum, 7) OVER (ORDER BY datepartition) AS prev_t7d,
  ROUND((t7d_sum - LAG(t7d_sum, 7) OVER (ORDER BY datepartition))
    * 100.0 / NULLIF(LAG(t7d_sum, 7) OVER (ORDER BY datepartition), 0), 1) AS wow_pct
FROM t7d
ORDER BY datepartition DESC
LIMIT 14
```

**Member Reports WoW (FA/ATO/Content):**
```sql
WITH daily AS (
  SELECT datepartition,
    flagging_reason,
    COUNT(*) AS reports
  FROM u_metrics.user_flagging_v3_union
  WHERE datepartition >= daysago(21)
    AND flagging_reason IN ('FAKE_ACCOUNT', 'ACCOUNT_HACKED', 'SPAM_OR_SCAM')
  GROUP BY 1, 2
),
t7d AS (
  SELECT datepartition, flagging_reason,
    SUM(reports) OVER (PARTITION BY flagging_reason ORDER BY datepartition ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS t7d_sum
  FROM daily
)
SELECT datepartition, flagging_reason, t7d_sum,
  LAG(t7d_sum, 7) OVER (PARTITION BY flagging_reason ORDER BY datepartition) AS prev_t7d,
  ROUND((t7d_sum - LAG(t7d_sum, 7) OVER (PARTITION BY flagging_reason ORDER BY datepartition))
    * 100.0 / NULLIF(LAG(t7d_sum, 7) OVER (PARTITION BY flagging_reason ORDER BY datepartition), 0), 1) AS wow_pct
FROM t7d
ORDER BY datepartition DESC, flagging_reason
LIMIT 30
```

## 2. Cohort-Based Metrics (Table 2)

For cohort-identified abusers, SEV is based on the harm the cohort is projected to generate.

**Baseline gate:** The cohort must contribute >= the gate % of total T7D for at least one metric before a SEV can be declared. This prevents small-denominator inflation.

| Metric Bucket | Metric | Gate | SEV 1 | SEV 2 | SEV 3 | SEV 4 |
|---------------|--------|------|-------|-------|-------|-------|
| IHE | Projected DIHE (invites and messages) | 10% | >100% | >70% | >60% | >50% |
| IHE | Projected DIHE (feed posts) | 10% | >100% | >70% | >60% | >50% |
| IHE | Projected DIHE (feed comments) | 10% | >100% | >70% | >60% | >50% |
| PVV | Projected Red PVV | 10% | >100% | >70% | >60% | >50% |
| Financial Loss | Telesign Cost | 10% | >40% | >25% | >20% | >15% |
| Data Egress | Projected Scraped Data | 1% | >100% | >70% | >60% | >50% |

### Cohort DIHE SQL Template

```sql
-- Cohort T7D DIHE for invites and messages
-- Replace {COHORT_MEMBER_IDS} with a subquery returning member_id
SELECT datepartition, 'cohort' AS source,
       COUNT(entity_urn) AS metric_value
FROM u_tds.fact_experience_base
WHERE datepartition >= daysago(36)
  AND experience_type IN ('RECEIVED_INVITATION', 'RECEIVED_MESSAGE')
  AND experience_creator_member_id IN ({COHORT_MEMBER_IDS})
GROUP BY 1

UNION ALL

SELECT datepartition, 'total' AS source,
       SUM(harmful_experience_7d_partial) AS metric_value
FROM u_metrics.account_abuse_harmful_experience_union
WHERE datepartition >= daysago(36)
  AND harm_type IN ('RECEIVED_INVITATION', 'RECEIVED_MESSAGE')
GROUP BY 1
ORDER BY source, datepartition
```

**Feed posts:** Replace harm types with `('VIEWED_HOME_FEED_UPDATE')`

**Feed comments:** Replace harm types with `('VIEWED_FEED_COMMENT')`

### Cohort Scraping SQL Template

```sql
SELECT datepartition, 'total' AS source,
       SUM(total_data_egress) AS metric_value
FROM u_metrics.scraping_member_data_egress_union
WHERE datepartition >= daysago(36)
  AND is_scraping = 1
GROUP BY 1

UNION ALL

SELECT datepartition, 'cohort' AS source,
       SUM(total_data_egress) AS metric_value
FROM u_metrics.scraping_member_data_egress_union
WHERE datepartition >= daysago(36)
  AND member_id IN ({COHORT_MEMBER_IDS})
GROUP BY 1
ORDER BY source, datepartition
```

### How to Compute T7D WoW from Raw Results

After running a cohort query, compute the derived metrics:
1. **Pivot** raw results into `date | cohort | total` columns
2. **T7D rolling sum** over 7-day windows for both cohort and total
3. **Baseline gate** = `cohort_t7d / total_t7d * 100` — must be >= gate %
4. **WoW %** = `(cohort_t7d - cohort_t7d_7days_ago) / cohort_t7d_7days_ago * 100`
5. **SEV assignment**: if gate passes AND WoW exceeds threshold → assign SEV

## 3. SEV Modifiers

### Risk Amplifiers (Boost +1 SEV)

| Criteria | Why Boost |
|----------|-----------|
| Has access to scaling factors (e.g. LSS) | Can rapidly scale the attack |
| Has Media / PR risk | Public attention amplifies harm |
| Has Privacy or Regulatory implications | Could trigger legal/regulatory action |
| Is causing an Ops queue backlog | Overwhelming operational capacity |
| Is Novel (e.g. MiTM attacks) | Unknown scope, requires discovery time |
| Multi-surface impact (>3 surfaces) | Broad spread across feed, invites, messages, etc. |

### Risk Reducers (Demote -1 SEV)

- Metric is trending back toward baseline (rate of increase slowing, stopped, or reversing)
- Maintain minimum SEV 4 until metric returns to baseline and stabilizes
- **Fresh UA string with weak non-UA signals:** If the phone builds spreadsheet shows the app/OS release date **close to the investigation date** and **other** abuse indicators are absent or scattered, treat volume spikes cautiously for SEV (see guardrail below). **Do not** withhold SEV when **other signals clearly** indicate abuse.

### Guardrail: User-agent IOCs and latest releases (phone builds spreadsheet)

Use this for UA-driven anomaly/volume alerts.

- Check [Latest phone builds & app versions](https://docs.google.com/spreadsheets/d/1ZGjZe5A0GBfWk27Mv02p6JyZvQkEh7QxFSLMMeJZlWY/edit?gid=0#gid=0), map UA app/OS to release date(s), compare to investigation/alert date, and log it.
- If release is recent, UA volume/anomaly/model score alone is **not** enough; require convergent non-UA abuse signals.
- Combine: restriction outcomes, model-vs-rules gap, email/domain/name patterns, geo/carrier concentration, registration method, temporal clustering.
- New app + older OS for device = warning flag, not proof.

**Examples**
1. `...4.1.1184...SM-A165F...android_16` + recent app/OS + scattered benign signals -> **not confirmed abuse**.
2. `...4.1.1184...SM-S9280...android_12` + older-OS mismatch + convergent abuse signals -> **abusive cluster can be supported**.

**SEV language guardrail**
- With recent release, do not set high SEV from UA count/Z-score alone.
- Do not call *active uncaught attack* from unrestricted %, model-vs-rules gap, Google sign-in share, geodistribution, and stable volume alone when email/geo are not attack-shaped.
- If recent release + scattered benign signals, prefer **inconclusive / possible scoring gap on new client**.

## 4. When to Merge SEVs

Merge two SEVs if either condition is met:
1. **Same abusive population** — e.g., both ATO self reports and ATO member reports spike from the same attackers
2. **Same MO** — e.g., FA member reports spike from NDA ≤30, then NDA >30 also doing the same OTW abuse

Take the most severe SEV when merging.

## 5. SEV Assessment Checklist

When assessing a SEV for an incident:

1. **Identify the metric(s) that spiked** — Is it a True North metric (Table 1) or cohort-based (Table 2)?
2. **Compute WoW T7D change** — Use the SQL templates above or the SevCalculatorWidget
3. **Check baseline gate** (cohort-based only) — Does the cohort contribute >= gate % of total?
4. **Determine base SEV** — Apply the threshold table
5. **Check modifiers** — Any amplifiers (LSS, PR risk, novel, multi-surface)? Trending down? If **UA-driven**, apply the **phone builds guardrail**: compare spreadsheet **release date(s) to the investigation date**; if **close**, require **convergent abusive** non-UA signals before high SEV — see phone builds spreadsheet
6. **Check for merge** — Are there other concurrent SEVs with same population or MO?
7. **Document** — State the metric, WoW %, gate %, base SEV, modifiers applied, final SEV

## DAVI Widget: SevCalculatorWidget

For **cohort-based metrics** (Table 2), the `SevCalculatorWidget` automates the full assessment with charts. Run via the `davi-runner` skill with `--notebook` for audit trail.

```python
from linkedin.davi.widgets import SevCalculatorWidget
widget = SevCalculatorWidget(cohort_member_ids="SELECT member_id FROM u_ir2fake.incident_cohort")
widget.run()          # Evaluates DIHE (invites/messages, feed posts, comments) + scraping
widget.show_report()  # Per-metric analysis with T7D charts, gate, WoW %, SEV
# Historical: SevCalculatorWidget(cohort_member_ids=..., datepartition="2026-02-15-00")
```

**Limitations:** Covers Table 2 only (not True North). No PVV/Telesign query templates yet. Does not apply SEV modifiers.

## Key Tables

| Table | Purpose |
|-------|---------|
| `u_metrics.gco_case_v2_union` | Self-reports (ATO, account compromise) |
| `u_metrics.user_flagging_v3_union` | Community member reports (FA, ATO, content) |
| `u_metrics.account_abuse_harmful_experience_union` | DIHE metrics (total harm by type) |
| `u_tds.fact_experience_base` | Cohort-level harm (by experience creator) |
| `u_metrics.scraping_member_data_egress_union` | Scraping data egress metrics |

## Historical SEV Counts (Past Year, from SEV doc)

| Metric | SEV 1 | SEV 2 | SEV 3 | SEV 4 |
|--------|-------|-------|-------|-------|
| Prevalence @ Response (T28D) | 0 | 3 | 4 | 8 |
| ATO self reports (T7D) | 4 | 7 | 8 | 11 |
| ATO member reports (T7D) | 2 | 4 | 5 | 8 |
| FA member reports (T7D) | 2 | 2 | 3 | 9 |
| Private Content Reports (T7D) | 2 | 3 | 5 | 9 |
| Public Content Reports (T7D) | 0 | 1 | 3 | 8 |

## Tips

- SEVs stop the bleeding — they trigger rapid containment when harm is newly emerging or accelerating
- Stable baseline abuse is not a SEV — that's for long-term defenses (models, coverage improvements)
- WoW change isolates step-change signal (new cohort or accelerating harm)
- For cohort metrics, projected DIHE/PVV account for partial enforcement coverage
- Pre-triage: take metric spikes at face value; post-triage: adjust up or down as investigation reveals root cause
- SEV levels can change during an investigation (e.g., spike was noise → demote; fanout revealed more accounts → promote)
