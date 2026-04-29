---
name: davi-runner
description: >-
  Run DAVI widgets and Python code on Darwin programmatically.
  Use when you need to execute DAVI widget code, run investigation notebooks,
  or query data via Darwin's Trino/Spark kernels.
allowed-tools: Bash
---

# DAVI Runner

Execute DAVI widgets and arbitrary Python on a Darwin pod via `darwin-local-client`.

## Tool

```bash
python3 tools/davi_runner.py <command>
```

## Commands

| Command | Description |
|---------|-------------|
| `setup` | One-time: clone darwin-local-client, create venv, install deps |
| `start` | Start proxy + kernel + connect to Darwin pod |
| `run "<code>" [--timeout N] [--notebook NAME]` | Execute Python code on the Darwin pod (default 600s) |
| `run-local "<code>" [--notebook NAME]` | Execute code on the local kernel (not Darwin) |
| `stop` | Disconnect from Darwin, stop kernel and proxy |
| `status` | Check if session is active |

All commands except `setup` output JSON: `{success, stdout, stderr, result, displays, error}`.

## First-Time Setup

```bash
python3 tools/davi_runner.py setup
```

This clones `lipy-darwin-local-client` to `/tmp/`, creates a venv, installs deps, and registers a kernel.
Only needs to run once (or after a reboot clears `/tmp`).

## Session Lifecycle

```bash
# Start (connects to Darwin — may take up to 150s for pod startup)
python3 tools/davi_runner.py start

# First time on a new pod: install lipy-davi
python3 tools/davi_runner.py run "
import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', 'lipy-davi'], capture_output=True)
print('installed')
"

# Run DAVI widget code with notebook audit trail
python3 tools/davi_runner.py run "
from linkedin.davi.widgets import SevCalculatorWidget
widget = SevCalculatorWidget(cohort_member_ids='SELECT member_id FROM ...')
widget.run()
widget.show_report()
" --notebook fake-account-inv-2026-03-23

# Stop when done
python3 tools/davi_runner.py stop
```

## Notebook Audit Trail

**IMPORTANT: Always pass `--notebook <NAME>` when running investigation queries and widgets.** This creates a persistent audit trail of all code executed and outputs returned.

### How it works

Every `run` or `run-local` call with `--notebook NAME` appends a timestamped code cell with full outputs to:

```
notebooks/<NAME>.ipynb
```

The notebook is created on first use and accumulates cells over the investigation. It can be opened in VS Code, Jupyter, or any notebook viewer to review charts, tables, and the full investigation history.

### Naming convention

Use descriptive names that tie to the investigation:

```bash
--notebook fake-account-inv-2026-03-23
--notebook ato-campaign-golden-grouper
--notebook scraping-investigation-TNS-317042
--notebook oncall-triage-2026-03-23
```

### Where to find notebooks

All notebooks are saved to the `notebooks/` directory in the repo root:

```
trustim-investigation/
  notebooks/
    fake-account-inv-2026-03-23.ipynb
    ato-campaign-golden-grouper.ipynb
    ...
```

### What gets saved

Each cell in the notebook contains:
- **Timestamp** as a comment at the top of the cell
- **Code** that was executed on Darwin
- **Outputs**: stdout (print statements), HTML (widget renders, charts, tables), errors

### JSON output

When `--notebook` is used, the JSON response includes the notebook path:

```json
{
  "success": true,
  "stdout": "...",
  "notebook": "notebooks/fake-account-inv-2026-03-23.ipynb"
}
```

## How It Works

1. **Proxy** (`jupyter-proxy`): Local HTTP/WebSocket bridge on `localhost:8889` to Darwin
2. **Kernel**: Local IPython kernel with the `darwin-local-client` magic extension loaded
3. **`run` command**: Sends code via `%%remote` magic → proxy → Darwin pod → output captured

DAVI widgets render HTML via `IPython.display`. The HTML comes back in the `displays` array of the JSON output.

## Authentication

The proxy uses `authn-cli` for Okta authentication. On first start, it may trigger a device auth flow.
If auth fails, check:
- `authn-cli` is installed and working
- Or set `DVTOKEN` env var manually

## Output Format

```json
{
  "success": true,
  "stdout": "printed text...",
  "stderr": "",
  "result": "last expression value",
  "displays": [
    {"type": "html", "data": "<table>...</table>"},
    {"type": "text", "data": "plain text display"}
  ],
  "error": null
}
```

DAVI widget output appears in `displays` as HTML. Use `stdout` for print statements.

## Available DAVI Widgets

All imported from `linkedin.davi.widgets`:

| Widget | Description |
|--------|-------------|
| `SevCalculatorWidget` | Calculate SEV level for abusive cohort based on DIHE metrics |
| `DiheWidget` | Analyze DIHE (harmful experience) metrics for fake/ATO accounts |
| `MagicPlotWidget` | Auto-plot DataFrames (line, bar, scatter, area, pie, etc.) |
| `AlertPlotWidget` | Visualize alerts: WoW spikes, IQR outliers, z-scores |
| `SurfaceVisualizationWidget` | Analyze registration traffic with NL filtering |
| `CaptainScrapingWidget` | Track scraping activity for a member |
| `IPActivityWidget` | Analyze search activity from IP perspective |
| `KeywordsAnalysisWidget` | Analyze search activity for specific keywords |
| `SearchTermRankingWidget` | Rank search terms by member IDs |
| `UaReviewAgenticWidget` | User agent analysis with restriction insights |
| `AgenticAnalyticsWidget` | AI-powered analytics from NL prompts |
| `GenericAgenticWidget` | Flexible LLM-powered widget for any data |
| `GaiProxyWidget` | Direct LLM proxy calls |
| `EmailWidget` | Send internal emails |
| `CopyFromClipboardWidget` / `CopyToClipboard` | Clipboard data I/O |

## Trino Setup (required for SQL-based widgets)

After `start`, run this to set up Trino before using any SQL-based widget:

```bash
python3 tools/davi_runner.py run "
get_ipython().run_line_magic('load_ext', 'linkedin.lisql')
get_ipython().run_line_magic('sql', 'trino://trino-holdem.prod.linkedin.com:443/hive')
get_ipython().run_cell_magic('sql', '', \"SET SESSION li_authorization_user = 'trustim'\")
print('Trino ready')
"
```

## Pod Timeout Recovery

If the pod times out (~30min idle), you'll get JSON parse errors. Reconnect without restarting:

```bash
python3 tools/davi_runner.py run-local "%remote --connect --new"
```

Then re-run the Trino setup above.

## Important Notes

- **Always use `--notebook` during investigations** — this is the audit trail
- `lipy-davi` must be pip-installed on the Darwin pod (first time per pod): `pip install lipy-davi`
- Import namespace is `linkedin.davi.widgets`, NOT `lipy_davi`
- Code runs on the Darwin pod's network — Trino, HDFS, Espresso are reachable
- Session state persists between `run` calls (variables, imports survive)
- IPActivityWidget, KeywordsAnalysisWidget, SearchTermRankingWidget need `gr003155` group for `tracking_live_daily.federatedsearchevent`
- State files live in `/tmp/davi-runner/`, notebooks in `notebooks/`
