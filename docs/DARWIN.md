# Darwin (notebooks, kernels, SQL) — usage from the productivity monorepo

`apps/darwin-runner/` and `lab darwin` were **retired on 2026-05-11**. Anything that needs to run code on a Darwin pod, query Trino/Spark, schedule notebooks, manage kernels, or deploy a DataApp now goes through the **`darwin-cli` Claude skill** — which wraps LinkedIn's hosted `darwin` CLI (`go/darwin`).

This doc is the short version. The authoritative reference is the skill itself.

## Where the skill lives

- Skill entry: `~/.claude/skills/darwin-cli/SKILL.md`
- Per-command reference files: `~/.claude/skills/darwin-cli/references/commands/<subcommand>.md`
- Multi-step workflows: `~/.claude/skills/darwin-cli/references/workflows.md`
- Binary on disk: `darwin` (installed via the Captain plugin system; `darwin --version` should print a version, otherwise run `darwin auth setup` / re-install the plugin).

When Claude is invoked with `darwin`/`jupyter`/`pyspark`/`trino`/`notebook` keywords, the `darwin-cli` skill auto-activates and tells the model exactly which subcommand to run, what flags it takes, and how to recover from common errors.

## API at a glance

| Capability | Commands |
|-----------|----------|
| Code execution | `darwin code execute`, `darwin sql execute`, `darwin pod shell` |
| Session save | `darwin code save-session`, `darwin sql save-session` |
| Notebook ops | `darwin notebook run`, `darwin notebook run-local`, `darwin notebook cell list/show/update` |
| Workbook runs | `darwin workbook run` |
| File transfer (laptop ↔ Darwin) | `darwin file upload`, `darwin file download`, `darwin file list` |
| One-off background runs | `darwin execution trigger/status/list/results/cancel` |
| Recurring (cron) schedules | `darwin schedule create/list/get/update/delete` |
| DataApp | `darwin dataapp deploy/list/status/stop/uninstall/restart/update/share` |
| DataApp schedules | `darwin dataapp schedule create/list/update/delete` |
| Charts / dashboards | `darwin chart create/modify/show/list`, `darwin dashboard create/list/show` |
| dbt / InDBT | `darwin dbt compile/run/test/build/seed/snapshot/deps/...`, `darwin dbt sandbox deploy/destroy/recreate/list-dags/trigger/run-status/task-logs/wait` |
| Pod | `darwin pod status`, `darwin pod restart`, `darwin pod image list/view` |
| Sessions / kernels | `darwin session list/get/clear`, `darwin kernel list [--running] / interrupt / restart` |
| Auth & certs | `darwin auth setup`, `darwin cert generate` |
| Notify | `darwin notify email` |
| Flink | `darwin flink pipeline …`, `darwin flink cluster …`, `darwin flink ddl execute`, `darwin flink query run`, `darwin flink convergence …` |
| Misc | `darwin update`, `darwin --help` |

The full natural-language → command table (with flags) is in `~/.claude/skills/darwin-cli/SKILL.md`. Always `Read` that file before running anything you haven't run before, and `Read` `references/commands/<subcommand>.md` for exhaustive flags.

## Quick recipes

```bash
# Trino SELECT (read-only; capped at 1000 rows)
darwin sql execute "SELECT * FROM hive.default.t LIMIT 100"

# Spark SQL (large reads, session reuse)
darwin sql execute --file query.sql --engine spark --session my-investigation

# Python on a Darwin kernel
darwin code execute --file plot.py --session my-investigation

# PySpark
darwin code execute --file job.py --kernel pyspark

# Run a notebook on the pod
darwin notebook run --path analysis.ipynb --from-cell 2 --to-cell 8

# Schedule a notebook
darwin schedule create --path report.ipynb --cron "0 9 * * *"

# Move files
darwin file upload   --src_path ./data.csv          --dest_path jcortes/data.csv
darwin file download --src_path jcortes/results.csv --dest_path ./results.csv

# Pod shell
darwin pod shell "pip install pandas"

# Auth recovery
darwin auth setup            # always the right answer for exit-code 2 (auth)
darwin -v sql execute "..."  # verbose mode for debug logs (auth, pod, WebSocket)
```

## Migration notes for old `lab darwin …` muscle memory

| Old (retired) | New |
|---|---|
| `lab darwin setup` | `darwin auth setup` (no separate venv to clone any more) |
| `lab darwin start` / `stop` / `status` | The `darwin` CLI manages the pod & kernels itself; `darwin pod status`, `darwin kernel list --running`, `darwin session clear` |
| `lab darwin run "<code>" --notebook X` | `darwin code execute --file <path> --session X` (or `darwin notebook run --path X.ipynb` for whole-notebook runs); use `darwin code save-session output.ipynb --session X` to capture an audit trail |
| `lab darwin run-local "<code>"` | `darwin notebook run-local <path>.ipynb` |
| `darwin-runner` symlink on PATH | Removed by `make install`; legacy `~/.local/bin/darwin-runner` is cleaned up by `make install` and `make uninstall`. |

## On error

- **Exit code 2 (auth):** `darwin auth setup`. Token expiry is otherwise handled automatically.
- **Exit code 5 (pod not ready):** wait ~2 min for cold start, retry. Check `go/darwin` in a browser.
- **Exit code 7 (WebSocket / kernel connection):** `darwin session clear --force`, retry.
- **`row_limit must be <= 1000`:** `sql execute` is capped at 1000 rows; paginate with `LIMIT/OFFSET`, or move into `code execute` for arbitrary sizes.
- **`Schedule` vs `Execution`:** `schedule *` manages cron *definitions*; `execution *` manages individual run history. "Did yesterday's run succeed?" is `execution list`; "what's the cron?" is `schedule get`.

For anything not covered here, read `~/.claude/skills/darwin-cli/SKILL.md` and `~/.claude/skills/darwin-cli/references/`.

---

## Running Darwin code inside the lab UI

The lab server (default `:3333`, overridable via `make start PORT=NNNN`) exposes a notebook executor that wraps `darwin code execute` and writes the result straight to an `.ipynb` on disk. Use it instead of running `darwin code execute` directly whenever you want the run to appear in an open notebook view (your UI **and** Claude Code can share the same notebook this way). Resolve the actual URL from any shell via `$(scripts/lab-url.sh)` so you never hardcode the port.

### Endpoint — `POST /api/nb/exec`

```json
{
  "path":   "projects/<id>/notebooks/<name>.ipynb",
  "code":   "print('hello darwin')",
  "kernel": "python3",      // optional: python3 | pyspark | spark-scala | r | python3-gpu
  "timeout": 600             // optional, seconds
}
```

Behavior:

- **Kernel session is pinned to the file.** The server derives a deterministic session id (`lab-<sha1[:12]>` of the relative path) so every cell appended to the same `.ipynb` lands on the same Darwin kernel. Variables persist between cells naturally.
- **The `.ipynb` on disk is the source of truth.** The endpoint loads the file (creating it if missing), appends a new code cell with the `cell_outputs` Darwin returned, bumps `execution_count`, and saves atomically.
- **The watcher does the rest.** Because the file lives under `content/`, the watcher fires `index-updated` on the WebSocket; every open notebook view in the SPA re-renders. The same flow works whether the run came from the UI's editor or from `curl` on a terminal.
- **Cell-level errors (NameError, SQL syntax, ...) still return 200** and land in the notebook as an `error` cell — the way Jupyter would. The endpoint only 4xx/5xx's when the `darwin` CLI itself fails (auth expired → 401, pod cold → 503, CLI missing → 503).

### From Claude Code

```bash
curl -s -X POST "$(scripts/lab-url.sh)/api/nb/exec" \
  -H 'Content-Type: application/json' \
  -d '{"path":"projects/<id>/notebooks/scratch.ipynb","code":"import pandas as pd; pd.__version__"}' | jq .
```

Open the notebook in the SPA: `$(scripts/lab-url.sh)/#/nb?path=projects/<id>/notebooks/scratch.ipynb`.

### Helpers

- `GET /api/nb/session?path=<rel>` — returns the pinned session id without running anything (useful for "which kernel is this notebook on?" lookups).
- `GET /api/nb?path=<rel>` — returns the parsed cells (the existing viewer endpoint).

