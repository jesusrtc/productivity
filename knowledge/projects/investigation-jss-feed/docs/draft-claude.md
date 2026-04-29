## Investigation Standards

### investigation.md structure

The investigation follows a funnel. Each step narrows the driver of the metric increase. Structure each step as:

1. Chart (time series)
2. Folded query block: `<details><summary>Query</summary>` with the SQL
3. 2-3 sentence summary stating the conclusion, not a play-by-play of the data

Only include findings that isolate or explain the increase. If a signal is evenly distributed across cohorts (e.g. every sub-type went up proportionally), it is not a signal and does not belong in investigation.md. Move it to a folded appendix or omit it entirely.

### Charts

**Only time series and stacked area charts.** No bar charts, no pie charts, no donut charts.

**Stacked area to decompose a total.** When you have a metric total (e.g. VIEWED_HOME_FEED_UPDATE T7D) and want to show which cohort is driving the increase, use a stacked area chart. The total is implicit (top of the stack). Do not plot the total as a separate line. Examples: ATO vs Non-ATO, Tier breakdown (T1/T2/T3/T4), Fake vs ATO vs Real.

**CASE WHEN to isolate an IOC.** When you identify a specific abusive cohort, show it against a baseline using a query like:

```sql
SELECT date,
  CASE WHEN <ioc_conditions> THEN 'Abusive Cohort' ELSE 'Other' END as cohort,
  SUM(metric) as value
FROM base_table
LEFT JOIN signal_table ON ...
GROUP BY date, cohort
```

This produces a two-line time series where the IOC spikes while "Other" stays flat, clearly showing what is driving the increase. Use LEFT JOIN from the official dashboard table so volumes match exactly.

**Always base on the official source-of-truth table** (e.g. `u_tdsjobseeker.job_seeker_safety_dash_dihe`), not on derived/event tables, so that the chart volumes match what leadership sees on the dashboard.

### File structure

- `investigation.md`: Working analysis. Charts + folded queries + minimal text.
- `one-pager.md`: Executive summary for leadership and broader team.
- `assets/`: All chart images. Referenced via `![title](assets/filename.png)`.
- `artifacts.json`: External links (Google Docs, Retina dashboards, JIRA) with brief descriptions.
- `actions.json`: Action items with status, deadlines, and blockers.

### Data approach

- Start from the dashboard table, drill down step by step.
- For account-level investigation, create a staging table (e.g. `u_ir2ato.<investigation>_abusers`) with all relevant member IDs to avoid repeating expensive queries.
- Use `trustim-investigation` skills for query templates.
- For non-time-series data (abuser profiles, login methods, WoW breakdowns), use tables in markdown instead of charts.

### Tools

- **Trino MCP** (`execute_trino_query`): For SQL queries. Read-only; use `trino query` CLI for DDL.
- **DAVI runner** (`tools/davi_runner.py run-local`): For matplotlib charts. Always pass `--notebook <name>` for audit trail.
- **CSTool Activity Viewer**: For per-account activity timelines. Paginated (50 events per page). Needs fresh Chrome cookies. Alternative: `u_trustim.event_cs_audit` table in Trino (has datepartition).

### Style

- Minimal prose. If a chart tells the story, the text just states the conclusion.
- No verbose bullet-point observations under charts. Two to three sentences max per step.
- Folded blocks (`<details>`) for queries, appendix material, and data that supports but doesn't drive the narrative.
