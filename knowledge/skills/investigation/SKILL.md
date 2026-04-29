# Investigation skill

Use when: a user pastes an alert, metric spike, Slack thread, or asks you to investigate a trust/safety signal.

## Structure (funnel)

Each investigation.md follows a narrowing funnel. Every step in the main investigation MUST have a chart — no chart, no step (move to appendix).

```
# <Title> Investigation

**Date:** YYYY-MM-DD | **Oncall:** Name | **Investigator:** Name

## 1. <First decomposition>
<2-3 sentence conclusion>
![Chart](assets/chart1.png)
<details><summary>Query</summary>

SELECT ...

</details>

## 2. <Deeper drill-down>
...

## N. Next Steps
- [ ] Action items

## Appendix
### Tables used
### Approaches tried
```

## IOC isolation

When you identify a specific abusive cohort, combine IOC signals into a CASE WHEN:

```sql
SELECT date,
  CASE WHEN <ioc_conditions> THEN 'IOC' ELSE 'Other' END as cohort,
  SUM(metric) as value
FROM base_table
LEFT JOIN signal_table ON ...
GROUP BY date, cohort
```

LEFT JOIN from the official dashboard table so volumes match exactly.

## Tools

- `apps/darwin-runner run-local --notebook <name>` for matplotlib charts
- `apps/darwin-backups q "..."` to search past notebooks for similar analyses
- `apps/trustim-ir-cli` for inResponse queries
- Dispatch `.claude/agents/intake-processor.md` for initial spike confirmation + glossary
- Dispatch `.claude/agents/query-reference.md` for table lookups

## Style

- Minimal prose. The chart tells the story.
- Non-time-series data (profiles, login methods) in tables in the appendix.
- Folded `<details>` blocks for queries.
