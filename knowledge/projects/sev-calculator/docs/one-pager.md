# SEV Calculator — One-Pager

**RFC:** https://docs.google.com/document/d/1KrGC9X9A7ipsHQwzEjWqn8GTbGDRwNYFBFtDvRitE4o
**SEV Definitions:** https://docs.google.com/document/d/163DM1Wu09zrJBnpCNMLE0MO0z51DiureZBPHk_qyzJU

## What It Does

Automated SEV (severity) calculator for abuse incidents. Given a cohort of abuser member IDs, it evaluates projected harm across multiple metrics using WoW (week-over-week) T7D (trailing 7-day) comparisons and recommends a severity level (SEV 1-4).

## Architecture

Lives in **lipy-davi** (`linkedin-multiproduct/lipy-davi`) as three layers:
- **SevCalculatorService** — pure computation: SQL queries, metric evaluation, SEV assignment
- **SevCalculatorWidget** — thin orchestrator for notebook/DAVI UI usage
- **SevCalculatorRenderer** — HTML/Plotly visualization

## Metrics Evaluated

### Currently Implemented (P0)
| Metric | Data Source | Baseline Gate |
|--------|-----------|---------------|
| Projected DIHE (invites/messages) | `u_tds.fact_experience_base` | 10% |
| Projected DIHE (feed posts) | `u_tds.fact_experience_base` | 10% |
| Projected DIHE (feed comments) | `u_tds.fact_experience_base` | 10% |
| Projected Scraped Data | `u_metrics.scraping_member_data_egress_union` | 1% |

### Not Yet Implemented
| Metric | Priority | Data Source |
|--------|----------|------------|
| Projected Red PVV | P1 | feed updates/comments viewed unions |
| Telesign Cost | P2 | TBD |

## SEV Thresholds (Cohort-Based, Table 2)

| Metric | SEV4 | SEV3 | SEV2 | SEV1 |
|--------|------|------|------|------|
| DIHE (all sub-categories) | >50% | >60% | >70% | >100% |
| Projected Red PVV | >50% | >60% | >70% | >100% |
| Telesign Cost | >15% | >20% | >25% | >40% |
| Projected Scraped Data | >50% | >60% | >70% | >100% |

## Calculation Logic

1. **Input:** Cohort member IDs (SQL subquery) + optional datepartition
2. **Query:** UNION ALL of cohort daily values + total daily values per metric
3. **T7D rolling sums:** 7-day trailing sum for both cohort and total
4. **Baseline gate:** cohort_t7d / total_t7d must be >= gate% (10% for DIHE, 1% for scraping)
5. **WoW % change:** (current_t7d - previous_t7d) / previous_t7d * 100
6. **SEV assignment:** Compare WoW% against thresholds; most severe qualifying SEV wins

## True North Metric Thresholds (Table 1 — NOT yet in calculator)

| Metric | Window | SEV4 | SEV3 | SEV2 | SEV1 |
|--------|--------|------|------|------|------|
| Prevalence@Response | T28D | >15% | >20% | >25% | >40% |
| ATO self reports | T7D | >15% | >20% | >25% | >40% |
| ATO member reports | T7D | >15% | >20% | >25% | >40% |
| FA member reports | T7D | >10% | >15% | >20% | >35% |
| Private Content Reports | T7D | >10% | >15% | >20% | >35% |
| Public Content Reports | T7D | >10% | >15% | >20% | >35% |

## SEV Definitions Doc — Key Details (DS/Grace)

- **SEV Modifiers:** Risk amplifiers (+1: LSS access, media/PR risk, privacy, novel attack, multi-surface) and reducers (-1: metric trending back)
- **SEV0:** Only via boosters on top of SEV1
- **Seasonality:** Exclude 6/27-7/10 and 12/21-1/4; use Wo2W/Wo3W during those periods
- **Closure criteria:** Week-over-Reference = (Current T7D - Reference) / Reference; close when below SEV4 threshold. Reference = T7D from week before SEV declared
- **48-hour SLA:** L1 analysis must complete within 48 hours
- **SLAs by level:** SEV0 = 2 days, SEV1 = 1 week, SEV2 = 2 weeks, SEV3 = 3 weeks, SEV4 = 4 weeks (+ up to 2 weeks observe)
- **DS onboarding:** New metrics need 90 days historical data, stable pipeline, formal definition
- **Working group:** Abhishek Chandak, Neel Amonker, Steven Yang, Grace Tang

## Merged PRs

1. **#181** — Initial SevCalculatorWidget (merged 2026-03-16)
2. **#200** — Fix NA crash in compute_metrics (merged 2026-03-25)
3. **#201** — Session context, investigation workflow, CLI improvements (merged 2026-03-31)
