---
name: code-asta-monitoring
description: >-
  Render an ASTA monitoring dashboard inline in a notebook — four
  Plotly figures (daily restrictions, ATO vs FAKE breakdown via
  `restriction_reasons[1]`, daily appeals + success rate, appeal
  outcomes by reason) plus headline tiles and a per-reason summary
  table. Two presets: 14-day recent and 180-day long-horizon. Invoke
  when the user says "asta dashboard", "monitor the ASTA", "stats for
  asta_<...>", "appeal rate for <ASTA job>", "ATO vs FAKE appeal
  success", "show me the restriction + appeal trend for <model_name>",
  or similar.
---

# code-asta-monitoring

A single Python function builds an ASTA monitoring dashboard. All four
charts pull from `u_metrics.restriction_appeal_union` (one query each,
no joins). The dashboard renders inline in the notebook cell — no HTML
file is written; nbconvert handles sharing if needed.

## How to invoke (Claude — just do this)

1. Make sure the project has the asta-monitoring notebook. If it's
   missing, copy it from any existing project that has one, or write a
   fresh one (template below). Canonical location:
   `projects/<id>/notebooks/asta-monitoring.ipynb`.

2. Run the bootstrap cell first (cell 0). It enables
   `linkedin.lisql`, sets the Holdem cluster + `trustim` proxy, and
   imports the function. Bootstrap is idempotent — re-running it is
   harmless.

3. Run the call cell for whichever preset / ASTA the user asked about.
   Each cell call renders inline in the lab UI notebook viewer.

Concretely, executing a cell via the lab server looks like this — pick
the cell that matches the user's request and only run that one:

```bash
NB=projects/<id>/notebooks/asta-monitoring.ipynb
LAB=$(scripts/lab-url.sh)

# Bootstrap (run once per fresh kernel — cell_index 1 in the template)
curl -sX POST "$LAB/api/nb/exec" \
  -H 'Content-Type: application/json' \
  --max-time 1500 \
  -d "$(jq -nc --arg path "$NB" --arg code 'import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
%reload_ext linkedin.lisql
%config SqlMagic.autocommit=False
%manage_trino Holdem
%set_proxyUser '"'"'trustim'"'"'
from code.asta_monitoring import asta_dashboard, asta_dashboard_recent, asta_dashboard_history' \
              '{path:$path, code:$code, timeout:1500}')"

# Recent (14d)
curl -sX POST "$LAB/api/nb/exec" \
  -H 'Content-Type: application/json' \
  --max-time 1500 \
  -d "$(jq -nc --arg path "$NB" --arg code 'asta_dashboard_recent("asta_off_platform_contact_spam")' \
              '{path:$path, code:$code, timeout:1500}')"

# History (180d)
curl -sX POST "$LAB/api/nb/exec" \
  -H 'Content-Type: application/json' \
  --max-time 1500 \
  -d "$(jq -nc --arg path "$NB" --arg code 'asta_dashboard_history("asta_off_platform_contact_spam")' \
              '{path:$path, code:$code, timeout:1500}')"
```

The lab-server's `code-runner-darwin` machinery handles the file
upload + import of `content/code/asta_monitoring.py` automatically —
just call the imported function inside the cell.

After the cell completes, open the notebook in the lab UI to see the
rendered figures:

```
$(scripts/lab-url.sh)/#/nb?path=projects/<id>/notebooks/asta-monitoring.ipynb
```

## Function API

```python
# content/code/asta_monitoring.py
def asta_dashboard(
    model_name: str,
    window_days: int = 14,
    start_datepartition: str | None = None,   # 'YYYY-MM-DD' or 'YYYY-MM-DD-HH'
    end_datepartition: str | None = None,     # default: today
) -> dict:
    """Render four Plotly figures inline + return the underlying DataFrames."""

def asta_dashboard_recent(model_name):   # window_days=14
def asta_dashboard_history(model_name):  # window_days=180
```

The model-name filter is `LIKE '<model_name>%'`, so version suffixes
(`_v1`, `_v2`…) are matched automatically. Pass the canonical
unsuffixed name, e.g. `"asta_off_platform_contact_spam"`.

Returns `{"daily": df, "by_reason": df, "appeals": df, "appeals_reason":
df, "headline": {...}}` so the calling cell can drill into raw data
without re-querying.

## What the dashboard shows

- **Headline tiles** — distinct restricted members, success appeals,
  false positives, success rate.
- **Daily restrictions** — line chart, distinct members per day.
- **Daily restrictions by reason** — multi-line, one trace per value
  of `restriction_reasons[1]`. This is where the ATO vs FAKE
  distinction shows up. (Don't read `accountlabel` on the tracking
  table — it's null for ASTA-emitted events.)
- **Daily appeals + success rate** — stacked bars for
  `appeal_success_yn` / `false_positive_yn` sums, with a secondary-axis
  success-rate line.
- **Appeal outcomes by reason** — grouped bar chart comparing
  ATO-restriction success appeals vs FAKE-restriction success appeals.
- **Per-reason summary table** — restricted members, success appeals,
  false positives, success rate for each reason.

## Data source (verified 2026-05-21)

Single table: `u_metrics.restriction_appeal_union`. Each row is a
(member, day, restriction) record from an ASTA; appeal columns are
populated when an appeal case exists.

| Field | Type | Use |
|-------|------|-----|
| `model_name` | varchar | filter (`LIKE '<name>%'`) |
| `member_id` | bigint | distinct-member counts |
| `restriction_reasons` | array&lt;varchar&gt; | element 1 = ATO_LOCKED / FAKE_ACCOUNT |
| `appeal_success_yn` | integer (0/1) | sum to count success appeals |
| `false_positive_yn` | integer (0/1) | sum to count false positives |
| `datepartition` | varchar `YYYY-MM-DD-00` | window filter |

The function accepts `start_datepartition` / `end_datepartition` in
either `YYYY-MM-DD` or `YYYY-MM-DD-HH` form; the hour is normalized to
`00` because that's the only hour the source table partitions on.

## Template — creating the notebook from scratch

If `projects/<id>/notebooks/asta-monitoring.ipynb` doesn't
exist, write it with these cells (the canonical version is the one in
`projects/asta-gofundme-revamp/notebooks/`):

- Markdown intro
- **Bootstrap cell** — imports + `%manage_trino Holdem` +
  `%set_proxyUser 'trustim'` + `from code.asta_monitoring import ...`
- One call cell per ASTA / preset, e.g.
  `asta_dashboard_recent("asta_off_platform_contact_spam")`
- A "custom window" cell with the explicit `start_datepartition` /
  `end_datepartition` example, commented out by default

## When this fails

- **Empty tiles + "(no data in window)" figures** — check the model
  name spelling. Try a partial name like `"asta_off_platform"` (the
  `LIKE '%'` suffix is auto-added). Try a longer `window_days`.
- **`Cell magic %%sql not found`** — the bootstrap cell didn't run on
  this kernel. Re-run cell 0 of the notebook.
- **`Catalog <x> not found`** — same root cause: bootstrap didn't run.
- **Trino timeout** — the window is too long; shorten `window_days` or
  pass narrower `start_datepartition` / `end_datepartition`.
- **`darwin timed out after 210s`** — the lab-server timeout fix from
  2026-05-21 wasn't applied. See `core/src/core/routes/nb_exec.py`
  (bootstrap timeout 180→900s, `body.timeout` upper bound removed).
