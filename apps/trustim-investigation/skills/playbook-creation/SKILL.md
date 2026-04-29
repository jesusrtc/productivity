---
name: playbook-creation
description: >-
  Guidelines for creating triage playbooks (investigation notebooks) and alerting playbooks
  (automated detection) following im_playbooks conventions. Use when building notebooks
  via davi-runner --notebook, or when the user asks to create a playbook or alert.
allowed-tools: Bash
---

# Playbook Creation Guidelines

Two types of playbooks exist in im_playbooks: **alerting playbooks** (scheduled detection → IRIS → InResponse) and **triage playbooks** (investigation after alert fires). When running investigations via `davi-runner --notebook`, Claude builds triage playbooks. Structure cells to match im_playbooks conventions so notebooks are reusable on Darwin.

## Notebook Types

There are two distinct types of playbooks:

| Type | Naming Convention | Purpose | Runs |
|------|------------------|---------|------|
| **Alerting Playbook** | `alert_{domain}_{signal}.ipynb` | Automated detection — detects metric spike, fires alert to IRIS, which gets ingested into InResponse | Scheduled on Darwin |
| **Triage Playbook** | `pb_{domain}_{name}.ipynb` | Investigation after alert fires — deep-dive analysis, audit trail, findings | Manual / Claude Code via `davi-runner` |

**When Claude builds notebooks via `--notebook`, it is building triage playbooks** — investigation audit trails with queries, widgets, and findings. Alerting playbooks are a separate concern (scheduled detection).

## Alerting Playbook Structure

Alert notebooks detect anomalies and fire IRIS incidents. Follow this cell order:

### Cell 1: Parameters

```python
# === Alert Parameters ===
IRIS_PLAN = 'trust-incident-auto-alert'  # or 'trust-incident-auto-alert-test' for testing
LOOKBACK_DAYS = 180           # Historical window for baseline
RECENT_DAYS = 15              # Only alert on spikes in recent N days
WOW_THRESHOLD = 20            # Week-over-week % increase to trigger
WO3W_THRESHOLD = 30           # Week-over-3-weeks % increase to trigger
ABSOLUTE_THRESHOLD = None     # Optional absolute count threshold
HEADLESS_ACCOUNT = 'trustim'  # Trino headless account
```

### Cell 2: Setup

```python
%reload_ext linkedin.lisql
%config SqlMagic.autocommit=False
%manage_trino Holdem
%set_proxyUser '{HEADLESS_ACCOUNT}'

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os, time, json
```

### Cell 3-5: Metric Aggregation (SQL)

Aggregate the target metric by week. LinkedIn uses **Saturday-Friday** weeks. Always include enough history for baseline (180 days).

```sql
%%sql
SELECT
    date_trunc('week', date(datepartition)) as week_start,
    COUNT(*) as metric_value
FROM {source_table}
WHERE datepartition >= date_format(date_add('day', -{LOOKBACK_DAYS}, current_date), '%Y-%m-%d-00')
GROUP BY 1
ORDER BY 1
```

### Cell 6-7: Threshold Computation

Calculate WoW and Wo3W changes. Filter to recent spikes.

```python
df['wow_pct'] = df['metric_value'].pct_change() * 100
df['wo3w_pct'] = df['metric_value'].pct_change(3) * 100

# Filter to recent anomalies
cutoff = pd.Timestamp.now() - pd.Timedelta(days=RECENT_DAYS)
recent = df[df['week_start'] >= cutoff]

wow_triggered = recent[recent['wow_pct'] >= WOW_THRESHOLD]
wo3w_triggered = recent[recent['wo3w_pct'] >= WO3W_THRESHOLD]
is_alert = not (wow_triggered.empty and wo3w_triggered.empty)
```

### Cell 8: Visualization

```python
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df['week_start'], df['metric_value'], marker='o')
ax.set_title(f'{METRIC_NAME} - Weekly Trend')
if is_alert:
    ax.axvline(x=wow_triggered.iloc[0]['week_start'], color='red', linestyle='--', label='Alert')
ax.legend()
plt.show()
```

### Cell 9: Alert Firing (IRIS)

```python
if is_alert:
    incident_data = {
        "title": f"Alert: {METRIC_NAME} spike detected",
        "reporter": os.environ.get("USER", "trustim"),
        "severity": "minor",
        "description": f"WoW increase of {wow_triggered.iloc[0]['wow_pct']:.1f}%",
        "source": "darwin-alert",
        "alert_date": str(wow_triggered.iloc[0]['week_start'].date()),
        "alert_metadata": json.dumps({
            "wow_pct": float(wow_triggered.iloc[0]['wow_pct']),
            "metric_value": int(wow_triggered.iloc[0]['metric_value']),
            "threshold": WOW_THRESHOLD,
        }),
        "playbook": "link to triage playbook"
    }
    # Post to IRIS
    import irisclient
    client = irisclient.IrisClient(app="liairp", key=api_key, api_host="https://iris.prod.linkedin.com")
    res = client.incident(IRIS_PLAN, incident_data)
    print(f"Alert posted: {res}")
else:
    print("No alert triggered")
```

## Triage Playbook Structure

Triage playbooks are run after an alerting playbook fires. They deep-dive into the anomaly. This is the type Claude builds via `davi-runner --notebook`. Follow this cell order:

### Section 1: Context & Setup

```python
# === Playbook: {Domain} Triage ===
# Alert reference: alert_{domain}_{signal}.ipynb
# Run this after an alert fires to investigate root cause.
#
# Parameters:
#   DATEPARTITION: Date of the alert (YYYY-MM-DD-00)
#   LOOKBACK_DAYS: Historical comparison window (default 90)

DATEPARTITION = '2026-03-18-00'
LOOKBACK_DAYS = 90
HEADLESS_ACCOUNT = 'trustim'
```

### Section 2: Metric Trends (90-120 day historical)

Plot the metric over time with breakdowns by:
- Restriction source (model, rule, manual)
- Damage type (invitations, messages, feed posts, comments)
- Payment status (free, premium, trial)
- Harm type (spam, fake, ATO, scraping)

### Section 3: Account Distribution

Pivot tables showing:
- Registration year distribution
- Top email domains
- Top countries (by IP)
- Restriction status (restricted vs unrestricted)
- Scoring signal distribution

### Section 4: Behavior Signals

Joins to behavioral tables:
- Premium/trial signups (free trial abuse)
- Handle/name changes (identity manipulation)
- Invitation/message activity (harm vectors)
- Top abusers ranked by victim count

### Section 5: Deep Dive (Top Abusers)

For the top 10-20 abusers:
- Member details (email, headline, IP, registration signals)
- Name change vs registration name comparison
- Device fingerprint clustering
- DAVI widget execution (DiheWidget, MagicPlotWidget)

### Section 6: Summary & Next Steps

```python
# === Investigation Summary ===
# Findings:
#   - {describe the anomaly pattern}
#   - {IOCs identified}
#   - {scope: N accounts, N victims}
#
# Recommended Actions:
#   - [ ] Post to #{domain} Slack channel
#   - [ ] File TNS for mass action (N accounts)
#   - [ ] Update detection rules
#   - [ ] Create IRIS incident if SEV warranted
```

## Statistical Alert Functions

The `im_playbooks` shared library provides these detection methods. Use them when building alert logic:

| Function | Method | Key Parameters |
|----------|--------|---------------|
| `compute_iqr_alert()` | Interquartile range outlier | `iqr_factor=1.5`, `rolling_window=21` |
| `compute_pct_above_rolling_avg()` | % above rolling average | `pct_threshold`, `rolling_window` |
| `compute_steady_increase_alert()` | N consecutive increases | `pct_threshold`, `continuous_periods` |
| `compute_pct_above_fixed_value_alert()` | Fixed baseline crossing | `fixed_value`, `pct_threshold` |
| `compute_zscore_alert()` | Z-score from rolling mean | `z_score_threshold`, `rolling_window` |
| `compute_period_over_period_increase_alert()` | YoY/QoQ comparison | `pct_threshold`, `overlay` (lag) |

All take a 2-column DataFrame (period, count) and return a result DataFrame with bounds + alert flag.

The DAVI `AlertPlotWidget` wraps these same methods with Plotly visualization:

```python
from linkedin.davi.widgets import AlertPlotWidget
AlertPlotWidget(df, alert_type="iqr", alert_params={"iqr_factor": 1.5, "rolling_window": 14}).run()
```

## Common Trino Patterns

### Headless accounts by domain

| Domain | Primary | Fallback |
|--------|---------|----------|
| General / triage | `trustim` | — |
| ATO | `ir2ato` | `trustim` |
| Fake accounts | `ir2fake` | `far` |
| Scraping | `ir2scraping` | `scrapeds` |
| Login | `login` | `trustim` |
| Registration | `register` | `trustim` |

### Partition format

Always `YYYY-MM-DD-00` for `tracking.*` tables. Dates are in **US Pacific time** by default. Use `daysAgo(N)` UDF or `date_format(date_add('day', -N, current_date), '%Y-%m-%d-00')`.

### Week aggregation

LinkedIn uses **Saturday-Friday** weeks. Use `date_trunc('week', date(datepartition) + interval '1' day) - interval '1' day` to align to Saturday starts, or use the `li_week_start()` UDF if available.

## Key Tables for Alerts

| Table | Use |
|-------|-----|
| `u_metrics.abuse_damage_fake_account_union` | FA impact metrics |
| `u_metrics.abuse_damage_ato_union` | ATO impact metrics |
| `u_metrics.account_abuse_harmful_experience_union` | DIHE (preferred over UMI) |
| `u_metrics.user_flagging_union` | Member reports |
| `u_metrics.restriction_appeal_union` | Restriction metadata |
| `prod_foundation_tables.dim_member_all` | Member profile enrichment |

## IRIS Incident Plans

| Plan | Use |
|------|-----|
| `trust-incident-auto-alert` | Production — automated alerts routed to InResponse |
| `trust-incident-auto-alert-test` | Testing — validates alert flow without creating real incidents |

## When Building Triage Playbooks via davi-runner

When using `davi_runner.py run --notebook`, Claude is building a **triage playbook**. Structure `run` calls to match the triage cell ordering above. Each `run` call becomes one cell in the notebook.

```bash
# Cell 1: Context + setup
python3 tools/davi_runner.py run "
# === Triage: Registration Spike (Alert 249973199) ===
# Alert date: 2026-03-18
# IOCs: spoofed Android UAs, clickregistration.lat domain
DATEPARTITION = '2026-03-18-00'
LOOKBACK_DAYS = 90
" --notebook pb-reg-spike-2026-03-18

# Cell 2: Metric trend query
python3 tools/davi_runner.py run "
result = get_ipython().run_cell_magic('sql', '', '''
SELECT date_trunc('week', date(datepartition)) as week_start, COUNT(*) as regs
FROM tracking.registrationevent
WHERE datepartition >= '2026-01-01-00'
GROUP BY 1 ORDER BY 1
''')
print(result.to_string())
" --notebook pb-reg-spike-2026-03-18

# Cell 3: Visualization via DAVI
python3 tools/davi_runner.py run "
from linkedin.davi.widgets import AlertPlotWidget
AlertPlotWidget(result, alert_type='wow', alert_params={'pct_threshold': 20, 'lag': 7}).run()
" --notebook pb-reg-spike-2026-03-18
```

The resulting triage playbook can be uploaded to Darwin for reuse. To convert it into an alerting playbook (scheduled detection), add the IRIS integration cells from the alerting playbook structure above.
