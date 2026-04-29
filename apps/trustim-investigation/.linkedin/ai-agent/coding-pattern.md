# Coding Patterns and Conventions

## Skill Architecture

### Investigation Skills vs Action Skills

Investigation skills define the workflow and reference action skills for SQL. Action skills under `skills/actions/`
contain reusable, parameterized SQL query templates. Investigation skills reference them by name (e.g., "Action:
`login-score-events` -> _MITM/Phishing Rule Detection_") rather than embedding SQL inline. See
`skills/oncall-triage/SKILL.md` for the reference pattern and `skills/actions/member-lookup/SKILL.md` for the action
pattern.

### Skill Frontmatter Convention

Every skill uses `allowed-tools: Bash` in the YAML frontmatter. The `description` field is a concise multi-line block
scalar describing when to use the skill.

### Query Construction Guidelines

All investigation skills include a standardized "How to Use This Skill" section with these rules:

1. Run `DESCRIBE {table_name}` before constructing queries
2. Build queries based on live schema, not templates
3. Always `GROUP BY` / `COUNT` / `COUNT(DISTINCT)` to aggregate
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII -- aggregate by IP org, email domain, country
6. Use Captain MCP tools for missing context

See `skills/common-reference/SKILL.md` for the canonical version of these guidelines.

## Python Patterns (`tools/davi_runner.py`)

### CLI Structure

The CLI uses a simple `if __name__ == "__main__"` dispatch pattern with `sys.argv` parsing. Each command is a separate
`cmd_*` function. No argument parsing library (argparse) is used; positional and `--flag` arguments are parsed manually
from `sys.argv`.

### JSON Output Convention

All tool output (except setup progress) is JSON on stdout via the `_json_out()` helper. Progress/status messages go to
stderr. The standard output schema is: `{success, stdout, stderr, result, displays, error}` with an optional `notebook`
field when `--notebook` is used.

### Process Management

PID files are stored in `/tmp/davi-runner/` using `_save_pid()`, `_is_alive()`, and `_kill()` helpers. Processes are
started with `start_new_session=True` so they survive parent exit. Status checks use `os.kill(pid, 0)` to test liveness
without sending a signal.

### Re-exec Pattern

`_ensure_dlc_python()` re-execs the script under the DLC venv Python using `os.execv()` when the current interpreter is
not the DLC venv. This ensures all DLC dependencies (jupyter_client, nbformat) are importable without requiring the user
to activate a venv.

### Notebook Audit Trail

The `_append_to_notebook()` function creates or appends to `.ipynb` files using `nbformat`. Each cell gets a timestamp
comment prefix (`# [YYYY-MM-DD HH:MM:SS]`). Notebook outputs map directly from the kernel execution result structure
(stdout, stderr, display_data, execute_result, error).

### Kernel Communication

`_execute_on_kernel()` uses `jupyter_client.BlockingKernelClient` to execute code and collect structured output. It
processes iopub messages in a loop, handling `stream`, `execute_result`, `display_data`, `error`, and `status` message
types. Remote kernel errors arriving via stderr are detected by checking for the `"Remote kernel error:"` prefix.

## Error Handling

- Tool errors return `{"success": false, "error": "..."}` JSON and `sys.exit(1)`
- Setup failures report specific remediation steps (e.g., "Run 'davi_runner.py setup' first")
- Kernel timeouts default to 600 seconds for `run` and 180 seconds for Darwin connection
- Graceful shutdown in `cmd_stop()` catches all exceptions during disconnect and cleanup

## Trino Query Conventions

- Headless account authorization: `SET SESSION li_authorization_user = '{account}';`
- Partition format: `YYYY-MM-DD-00` (US Pacific time)
- Date functions: `daysAgo(N)` UDF or `date_format(date_add('day', -N, current_date), '%Y-%m-%d-00')`
- Week alignment: LinkedIn uses Saturday-Friday weeks
- Use `element_at(params, 'key')` to extract from map columns
- Join login events with score events on `submissionid` / `element_at(params, 'submissionId')`

## Investigation Conduct Rules

The `CLAUDE.md` file defines mandatory investigation behavior rules that override all default behavior. Key patterns:

- **Never assume** -- always ask the user before running queries about scope, date range, and metrics
- **Audit trail required** -- Google Doc + notebook for every investigation
- **Query-before-claim** -- never state a number without a corresponding query result
- **Conversational flow** -- propose plan, run query, show results, ask for direction
- **Explicit uncertainty** -- flag insufficient data and conflicting evidence
- **SEV discipline** -- always check thresholds from `sev-assessment` skill before assigning severity
