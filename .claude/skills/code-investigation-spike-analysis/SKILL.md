---
name: code-investigation-spike-analysis
description: >-
  Decompose a trust & safety metric spike into the (column, value) pairs
  that best explain it — ranked by precision (how concentrated this
  value's volume is in the spike window vs the baseline-extrapolated
  expectation) and recall (how much of the spike's extra volume this
  value captures). Backed by a Trino CROSS JOIN UNNEST(MAP(...)) trick
  that analyzes every categorical column in one query. Invoke when the
  user says "why did X spike", "decompose this spike", "find the IoC
  for this spike", "what's driving the spike on <table>", "run spike
  analysis on …", "break down the registration / login / scraping /
  ATO spike", or "what changed during this incident window".
---

# code-investigation-spike-analysis

Two ways to call it. Pick `analyze_table` when the data already lives in
a flattened table (`u_trustim.event_*`, `u_trustim.dim_*`, your own
team views). Pick `analyze_sql` when you need to JOIN tables, scope a
filter, or stitch ad-hoc rows together for the investigation. Same
return shape; same precision/recall table.

## Function API

```python
# content/code/spike_analysis.py

def confirm(sql: str, *, title: str = "Spike",
            time_column: str = "str_time",
            metric: str = "count(*)") -> None:
    """Quick spike sanity check — spin up a temp view, plot the metric
    over time, drop the view. Use this BEFORE committing to a full
    analyze_*; if there's no visible spike here, save yourself the
    feature-query cost."""

def spike_makes_sense(*, spike_start_date, spike_end_date,
                      baseline_start_date, baseline_end_date,
                      baseline_avg=None, spike_avg=None,
                      spike_increase_pct=None, spike_periods=None,
                      min_increase_pct=10.0) -> dict:
    """Warn-only check. Returns {ok, warnings, hard_fails}. Flags
    spike_end on/after today (latest partition incomplete), empty
    baseline, ≤1 spike period, sub-noise increase. Called automatically
    by analyze_* — printed warnings continue by default; pass
    force=True to silence."""

def analyze_table(*, source_table: str,
                  spike_start_date: str, spike_end_date: str,
                  baseline_start_date: str, baseline_end_date: str,
                  date_column: str = "datepartition",
                  where: str = "",
                  metric: str = "count(*)",
                  plot: bool = True, force: bool = False,
                  min_recall: float = 30.0,
                  min_precision: float = 60.0,
                  min_percentage_increase: float = 5.0,
                  include_columns: list[str] = None,
                  exclude_columns: list[str] = None,
                  max_charts: int = 10,
                  title: str = "Spike analysis") -> dict:
    """Run spike analysis against a flattened table — no temp view.
    Best for u_trustim.event_*, u_trustim.dim_*, and any pre-built
    view. `where=` takes a predicate without the leading AND."""

def analyze_sql(sql: str, *, title: str,
                time_column: str = "str_time",
                spike_start: str, spike_end: str,
                baseline_start: str, baseline_end: str,
                metric: str = "count(*)",
                plot: bool = True, force: bool = False,
                min_recall: float = 30.0,
                min_precision: float = 60.0,
                min_percentage_increase: float = 5.0,
                include_columns: list[str] = None,
                exclude_columns: list[str] = None,
                max_charts: int = 10) -> dict:
    """Run spike analysis from raw SQL — creates a temp view at
    u_ir2fake.tmp_<slug>_<ts>, runs the pipeline, drops the view.
    The SQL must SELECT a column named by `time_column`."""
```

Both `analyze_*` return:

```python
{
  "metrics": {"baseline_avg": ..., "spike_avg": ...,
              "spike_increase_pct": ..., "estimated_spike_val": ...,
              "spike_periods": ..., "baseline_periods": ...},
  "features_df": DataFrame,        # PRECISION/RECALL TABLE — the primary output
  "timeseries_df": DataFrame|None, # populated only when plot=True
  "sanity":     {"ok": bool, "warnings": [...], "hard_fails": [...]},
}
```

## What the precision/recall table tells you

For each surviving `(column, value)` pair:

| Column | Meaning |
|---|---|
| `column` | Which column in the source data |
| `value` | The specific value within that column |
| `baseline_val` / `spike_val` | Raw event counts in each window |
| `percentage_during_baseline` / `percentage_during_spike` | Share of total events in each window (a "share shift" view) |
| `percentage_diff` | Spike share − baseline share (positive = this value gained share) |
| `recall` | What % of the spike's *extra* volume this value explains. `recall ≥ 90` ⇒ this single dimension explains the spike |
| `precision` | What % of this value's spike-window volume is *above* the baseline-extrapolated expectation. `precision ≥ 90` ⇒ this value is highly spike-specific, not just noise that scales with baseline |
| `estimated_total_fp` | How many of this value's spike-window events were "expected" from baseline rate × spike periods (the false-positive floor) |

**Default thresholds:** `min_recall=30`, `min_precision=60`,
`min_percentage_increase=5`. Loosen these for noisy data; tighten when
you only want the cleanest signal. Setting all three to `0` returns
every analyzed pair.

## Call snippets

### Use a flattened table from u_trustim (most common during oncall)

```python
from code.spike_analysis import analyze_table

result = analyze_table(
    source_table="u_trustim.event_registration",
    date_column="datepartition",
    spike_start_date="2026-05-12-00",
    spike_end_date="2026-05-12-23",
    baseline_start_date="2026-05-05-00",
    baseline_end_date="2026-05-11-23",
    where="country_code = 'US'",  # optional extra filter
)
result["features_df"]  # precision/recall table
```

### Build an ad-hoc view from SQL (for joined / filtered data)

```python
from code.spike_analysis import analyze_sql

result = analyze_sql(
    """
    SELECT e.*, d.email_domain
    FROM u_trustim.event_registration e
    LEFT JOIN u_trustim.dim_email_address d
      ON e.member_id = d.member_id
    WHERE e.datepartition BETWEEN '2026-05-10-00' AND '2026-05-12-23'
    """,
    title="registration-spike-with-email-domain",
    time_column="str_time",
    spike_start="2026-05-12 15:00",
    spike_end="2026-05-12 17:00",
    baseline_start="2026-05-10 00:00",
    baseline_end="2026-05-11 23:00",
)
```

### Confirm there's actually a spike first (cheap)

```python
from code.spike_analysis import confirm

confirm(
    "SELECT * FROM u_trustim.event_registration "
    "WHERE datepartition BETWEEN '2026-05-10-00' AND '2026-05-12-23'",
    title="registration",
    time_column="str_time",
)
```

### Skip plotting for fast iteration

```python
result = analyze_table(
    source_table="u_trustim.event_login",
    spike_start_date="2026-05-12-15", spike_end_date="2026-05-12-17",
    baseline_start_date="2026-05-05-00", baseline_end_date="2026-05-11-23",
    plot=False,
)
# Inspect the table without paying for charts
print(result["features_df"].head(20))
```

## When to use which entry point

- **`u_trustim.*` already has the right schema** (a single row per event
  with all the dimensions you want decomposed) → `analyze_table`.
- **You need to JOIN dim/event tables, derive a new column, or filter
  by something complex** → write the SELECT and pass to `analyze_sql`.
  The temp view persists for the duration of the call and is dropped
  cleanly.
- **You want to test if a metric is really spiking before paying for
  the full feature query** → `confirm`.
- **You're not sure your window makes sense** → run
  `spike_makes_sense(...)` first with just the dates; it returns the
  warning list without hitting the DB.

## The sanity gate

Before the expensive feature query runs, `spike_makes_sense()` flags:

- `spike_end_date` is on or after today → latest datepartition is
  almost certainly incomplete. The "spike" may just be ingestion lag.
  Move the spike window back to the last fully-closed period.
- Baseline window has no data (`baseline_avg = 0`).
- Spike window has 0 or 1 periods (not enough to call a trend).
- Spike increase is below the noise floor (`< 10%` by default).

Warnings print and the analysis continues. Pass `force=True` to suppress
the printed warnings (they still come back in `result["sanity"]`).

## Expected output

A typical call produces, in order:

1. ⚠️ Sanity warnings (if any).
2. Headline numbers (baseline/spike avg, increase %, est. extra volume).
3. Overview line chart with baseline/spike windows as vertical dotted
   lines and avg-per-period as horizontal dotted lines. _(skipped when
   `plot=False`)_
4. **Precision/recall table** — every `(column, value)` that cleared
   the thresholds, sorted by `percentage_diff` desc. This is the
   primary IoC list.
5. Per-feature subsections (when `plot=True` and `max_charts > 0`):
   the relevant rows of the table for one column, then an area chart
   binning the top values vs `"Other"` over the full window.
6. Human-readable Markdown summary: top-3-ish indicators with
   one-line verdicts (`Strong clean signal`, `Primary driver`,
   `Specific to the spike`, `Secondary IoC`, `Correlated but not primary`).

## When this fails

| Symptom | Likely cause | Fix |
|---|---|---|
| `Spike metrics query returned no rows` | `date_column` doesn't match the table's real partition column | `DESCRIBE u_trustim.<table>` and pass the right name. |
| `No analyzable columns after filtering` | All columns are date/id/complex types | Pass `include_columns=[...]` with explicit names, or widen the type allowlist. |
| `**No (column, value) pairs cleared the precision/recall thresholds.**` | Thresholds too tight, or there's no clear concentrated signal | Drop `min_recall` to 10, `min_precision` to 30. If still empty, the spike may be a uniform multiplier across all dimensions (volume attack, not signature attack). |
| Plot section silent / empty area charts | `linkedin.davi.plot` not loaded after bootstrap | The module falls back to plain plotly; if that also fails, the precision/recall table is still in `result["features_df"]`. |
| Temp view leaked after `analyze_sql` | Cell errored mid-pipeline (e.g., kernel restart) before `__exit__` | Manually `DROP VIEW IF EXISTS u_ir2fake.tmp_<slug>_<ts>`. |

For plumbing issues (cell never lands in the notebook, kernel cold
start, lipy-davi install failure) see **`code-runner-darwin`**.
