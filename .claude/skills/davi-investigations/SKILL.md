---
name: davi-investigations
description: >-
  Build the signature IoC-over-time chart for investigation and ASTA
  one-pagers. Provides the 3-column SQL contract (time, label, count)
  and the one-line `linkedin.davi.plot()` recipe. Use when an
  investigation or ASTA one-pager needs the spike-attribution stacked
  bar chart that visually demonstrates an IoC explaining a metric move.
  Triggers: "plot the IoC over time", "signature chart for this
  investigation", "spike attribution chart", "coverage chart for this
  ASTA", "IoC vs other chart".
---

# DAVI investigations — IoC over-time chart

Consumed by:

- `one-pager-investigation` — the signature chart directly under the TLDR.
- `one-pager-asta` — the rule coverage chart in Key Metrics.

## The 3-column SQL contract

The SQL must emit **exactly three columns in this order** — that's what
`davi.plot()` consumes:

1. **time** — any string `davi.plot` can parse: `YYYY-MM-DD`,
   `YYYY-MM-DD HH:00`, `YYYY-Www`, etc. Use day buckets unless the spike
   is so tight you need hour buckets.
2. **label** — the category to split / stack by. Two values is the
   canonical shape: the IoC label (human-readable) and `'Other'`.
3. **n** — integer count.

### SQL shape

```sql
SELECT
  substr(datepartition, 1, 10) AS day,
  CASE
    WHEN <ioc predicate>
      THEN '<Human-readable IoC label, e.g. "Logged in with unfamiliar device and updated email handle">'
    ELSE 'Other'
  END AS label,
  COUNT(*) AS n
FROM <source table>
WHERE datepartition >= '<baseline_start>'
GROUP BY 1, 2
ORDER BY 1, 2
```

### Plot it (one line)

```python
%%sql ioc_df <<
<the SELECT above>
;;

from linkedin.davi import plot
plot(ioc_df, title="<Metric> daily — IoC vs Other")
```

`plot()` infers the time column, the split column, and the count from
the 3-column shape; it picks colors, stacks the bars, renders to the
notebook, and saves a PNG copy to `assets/`. No raw Plotly. No
`write_image` calls. No color maps.

### Output convention

| Caller | PNG path |
|---|---|
| Investigation | `content/projects/<id>/assets/<slug>_ioc_over_time.png` |
| ASTA coverage | `content/projects/<id>/assets/<slug>_coverage_over_time.png` |

The one-pager skills reference these paths in their markdown embeds.

## Worked example (Feed DIHE Spike, March 2026)

```python
# Cell 1 — SQL: returns (day, label, n)
%%sql ioc_df <<
SELECT
  substr(datepartition, 1, 10) AS day,
  CASE
    WHEN ato_tier IN (1, 2) AND mlc_label = 'FourByFour'
      THEN 'ATO T1/T2 FourByFour'
    ELSE 'Other'
  END AS label,
  COUNT(*) AS n
FROM u_trustim.flatten_harmful_experiences
WHERE datepartition BETWEEN '2026-03-09' AND '2026-04-01'
  AND harm_type = 'VIEWED_HOME_FEED_UPDATE'
GROUP BY 1, 2
ORDER BY 1, 2
;;

# Cell 2 — Plot
from linkedin.davi import plot
plot(ioc_df, title="Feed DIHE daily — IoC (ATO T1/T2 FourByFour) vs Other")
```

Result: a stacked bar where the IoC segment grows sharply from Mar 22
onward and dominates the spike — visually closes the "what caused
this?" question before the reader gets to the drill-down table.

## Run it through the lab notebook executor

Always send these cells via `POST http://localhost:3333/api/nb/exec`
(not `darwin code execute` directly), so the notebook becomes a durable
artifact and the lab UI shows the chart live. See
`content/projects/CLAUDE.md` in the monorepo for the recipe.

## Rules

- Three columns, that exact order: `time`, `label`, `n`.
- Label = IoC name vs `'Other'` (two-value canonical shape).
- `from linkedin.davi import plot; plot(df, title="…")` — that's it.
  No raw Plotly, no manual color mapping, no `fig.write_image`.
- PNG output path: `assets/<slug>_ioc_over_time.png` (investigation) or
  `assets/<slug>_coverage_over_time.png` (ASTA coverage).
- Other chart patterns (drill-down precision/recall tables, cohort
  timelines, funnel charts) can be added here later if they become
  recurring. For now this skill owns the IoC over-time chart only.
