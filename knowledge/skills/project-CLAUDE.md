# Project orientation (shared)

**This file is symlinked into every `knowledge/projects/<id>/CLAUDE.md`.**
Edit the source in `knowledge/skills/project-CLAUDE.md` — all projects
pick the change up on next Claude session.

## How to call `lab`

Prefer `~/.local/bin/lab` for scripts/automation; it bypasses any
conflicting `lab` binary that may sit earlier on `$PATH` (miniconda
ships one that shadows ours on some setups). If `which lab` points at
something other than `~/.local/bin/lab`, either:

- run `~/.local/bin/lab …` directly (safest),
- or invoke the in-repo venv from the monorepo root:
  `apps/lab/.venv/bin/python -m lab …`,
- or fix your shell rc to put `~/.local/bin` first on `$PATH`.

`make install` prints a loud warning when this conflict is detected.


Per-project state lives in this directory's **`project.json`** (name,
description, status, priority, due, tags, labels, worktrees, PRs, artifacts,
pinned docs) and **`tasks.json`** (task list). Read those for current
context on session start:

```bash
cat project.json        # project identity
cat tasks.json          # backlog + in-progress
lab project status      # short summary of both
lab task ls             # task list with status/priority
```

Never hand-edit these files — use the `lab` CLI. The web UI at
`http://localhost:3333/p/<project-id>` renders them live.

---

## lab CLI — the unified write path

### Project

```
lab project new <id>  [--desc ...] [--priority P0/P1/P2/P3] [--due YYYY-MM-DD]
                       [--tags a,b] [--labels mp-name,...]
lab project ls       [--status active|paused|done|archived|all]
lab project status   [id]           # defaults to PWD's project
lab project set <id> <field> <value>  # field ∈ description, status, priority,
                                      #          due, loe, tags, labels, name
lab project archive  <id>
lab project rm       <id>           # permanent delete (confirm)
lab project add      <id> <mp>      # create a git worktree of <mp> inside the project
                                    # branch name defaults to jcortes/<objective>
                                    # pulls repositories/ first if missing
lab project remove   <id> <mp>      # `git worktree remove` + project.json cleanup
lab project relink  [--all|--id ID] # re-symlink CLAUDE.md to this shared file
```

### Tasks

```
lab task new <title> --project <id> --priority P0|P1|P2|P3
                     [--loe N] [--due YYYY-MM-DD] [--tags ...] [--labels ...]
                     [--file]                 # also create a notes/<id>.md file
lab task ls  [--project <id>] [--status ...] [--priority P0,P1]
lab task done      <task-id> --project <id>
lab task reopen    <task-id> --project <id>
lab task block     <task-id> "<reason>" --project <id>
lab task unblock   <task-id>              --project <id>
lab task set       <task-id> <field> <value> --project <id>
```

### Repositories + worktrees

```
lab repo ls                 # repos under repositories/ with their prefix
lab repo prefix <mp> <short>
lab repo pull [--only <mp>]          # clone / update from repositories.list
                                     #   (same as `make pull-repos`)
```

Worktrees live at `knowledge/projects/<id>/<prefix>-<objective>/` on a
branch derived from the project id. Use `lab project add <id> <mp>` — it
bootstraps repositories/ first if the MP isn't cloned yet.

### PRs + artifacts

```
lab pr add <url> --project <id> [--mp ...] [--title ...] [--status open|merged|closed]
lab pr rm  <idx> --project <id>
lab artifact add <url> --project <id>
                       [--type google_doc|spreadsheet|confluence|github|jira|slack|url|...]
                       [--title ...] [--desc ...]
                       [--file docs/one-pager.md]   # pin the artifact to a local doc
lab artifact rm  <idx> --project <id>
```

### Linking local docs to their online versions

Any project doc that has an online canonical form (Google Doc one-pager,
Confluence page, shared sheet, external spec) should have an artifact
entry with `--file <relative-path>`. The web UI shows a "📎 Published at"
banner on that doc so the next reader goes to the canonical source
instead of editing the local copy in isolation.

**When writing or editing a doc, always:**

1. Ask the user: *"Is this already published online? If so, paste the
   link and I'll attach it."* If yes:
   ```
   lab artifact add "<url>" --file docs/one-pager.md --type google_doc --title "<title>"
   ```
2. If a doc later gets published (user exports to GDoc after review),
   run the same command to attach the link.
3. Before suggesting edits to a linked doc, warn that the online copy
   may need the same update. Offer to generate a copy-paste rich-text
   block (via the "📋 Copy" button in the UI).

PRs and commits already serve the same "online mirror" role for code —
`lab pr add` covers that side; `--file` covers the doc side.

Readers can also set this link from the UI via the 🔗 Link button in
the doc header — it writes to the same `project.json.artifacts[]`
location.

### References (reading material the project depends on)

Two complementary ways to tie a project to external context. Read these
when you need background — they're deliberately curated, not every
artifact the project might someday touch.

**Internal links — `links/` folder.** Symlinks into docs that live
elsewhere in the monorepo (another project's one-pager, a shared wiki
under `knowledge/wikis/`, meeting notes). They render in the sidebar
like local docs without duplicating content. The folder auto-expands in
the UI.

```bash
cd knowledge/projects/<id>
lab link add ../other-project/docs/one-pager.md      # -> links/one-pager.md
lab link add knowledge/wikis/platform.md             # -> links/platform.md
lab link add ../bar/docs/vision.md --name bar-vision # -> links/bar-vision.md
lab link ls
lab link rm bar-vision
```

When reading a project, treat everything under `links/` as primary
context — same weight as the project's own `docs/`. The symlinks point
at live files, so any edit to the original shows up immediately.

**External references — URLs stored in `project.json`.** For links that
live outside the monorepo (articles, Slack threads, blog posts, external
specs). They surface in the sidebar as a virtual `external-references/`
folder with the title + 🔗 icon; clicking opens the URL in a new tab.

```bash
lab ref add https://go/foo-design --name "Foo design doc"
lab ref add https://example.com/article                    # name defaults to URL
lab ref add https://slack/... --name "Scoping thread" --note "why we picked bar over baz"
lab ref ls
lab ref rm 2
```

Distinct from `lab artifact` — artifacts are canonical online mirrors of
**local work we authored** (Google Doc one-pager, Confluence page);
references point **inbound** (context we consume, not content we own).

When summarizing or answering questions about a project, scan both
`links/` and `references[]` — they're the hand-picked reading list.

### Search + index

```
lab search "<query>"          # grep across projects, tasks, and knowledge/ docs
lab index rebuild             # rebuild knowledge/.index.json
lab index show                # dump the current index
```

### Darwin analyses (Trino / PySpark / matplotlib on the Darwin pod)

When the user asks you to run an analysis, a Trino query, or produce a
chart, use `lab darwin` — it executes code on a persistent Darwin kernel
and appends each run (code + stdout + rendered HTML/PNG + errors) as a
cell to `notebooks/<project-id>.ipynb`. The web UI renders the notebook
inline under the project's FILES sidebar and refreshes live.

```bash
# One-time (creates the lipy-darwin-local-client venv under /tmp/).
lab darwin setup

# Once per working session (launches jupyter-proxy + establishes pod).
lab darwin start

# Run an analysis. Must be executed from inside the project directory
# (knowledge/projects/<id>/) so darwin-runner picks up project.json.
cd knowledge/projects/<id>

# Canonical recipe: SQL → DAVI plot → summary stats. Write to a file
# (avoids shell-quoting collisions with `interval '14' day`, f-strings,
# etc.) and run via --file. See "Quoting gotcha" below.
cat > /tmp/analysis.py <<'PY'
# %sql is a line magic — keep the query on one line (backslash
# continuation doesn't work inside lisql magics). The heredoc is
# single-quoted so inner quotes and % signs pass through unchanged.
df = %sql SELECT substr(datepartition, 1, 10) AS day, COUNT(*) AS registrations FROM tracking.registrationevent WHERE datepartition >= date_format(current_date - interval '14' day, '%Y-%m-%d-00') AND datepartition < date_format(current_date, '%Y-%m-%d-00') GROUP BY 1 ORDER BY 1
df  # displays the dataframe as a table in the notebook

from linkedin.davi import plot
import pandas as pd

d = df.copy()
d['day'] = pd.to_datetime(d['day'])
d = d.sort_values('day')

# DAVI's plot() renders via MagicPlotWidget — the productivity UI renders
# it the same way Plotly notebook cells render (with the AMD shim now in
# place). Default to this. Reach for matplotlib only if plot() can't do it.
plot(
    d,
    x='day',
    y='registrations',
    title='Daily registrations — last 14 days (tracking.registrationevent)',
)

total = d['registrations'].sum()
mean  = d['registrations'].mean()
mn    = d['registrations'].min()
mx    = d['registrations'].max()
print(f'Total over {len(d)} days: {total:,}')
print(f'Mean daily: {mean:,.0f}')
print(f'Min/max:   {mn:,} / {mx:,}')
PY
lab darwin run --file /tmp/analysis.py

# Tear down when done (clears the stored kernel_id).
lab darwin stop
lab darwin status
```

**Quoting gotcha:** `lab darwin run '<code>'` shells through zsh. Inner
SQL that needs single quotes (`interval '14' day`) or an f-string with a
backslash will collide with the outer quoting. For anything multi-line
or quote-heavy, use `--file` instead:

```bash
cat > /tmp/analysis.py <<'PY'
from linkedin.davi import plot
df = %sql SELECT substr(datepartition, 1, 10) AS day, COUNT(*) AS c
         FROM tracking.myevent
         WHERE datepartition >= date_format(current_date - interval '14' day, '%Y-%m-%d-00')
plot(df, x="day", y="c", title="14d volume")
PY
lab darwin run --file /tmp/analysis.py
```

**Auth preflight.** `darwin-runner` relies on dvtoken / captain auth
cache. If `lab darwin start` stalls past ~60s with no response, check
for a leftover `authn-cli` process from a prior aborted attempt
(`ps aux | grep authn-cli`) and kill it. If the dvtoken is expired,
refresh via `captain setup darwin`.

**When `start` fails partway through:** proxy may already be running
while the remote-kernel handshake failed. Retry with `lab darwin start
--force` — it tears down the proxy first and restarts the whole thing
idempotently. `lab darwin status` shows whether the proxy is up.

**Cleanup / hard reset.** For a fully wedged state (stale proxy,
orphaned authn-cli, cached venv out of date):

```bash
lab darwin stop
rm -rf /tmp/davi-runner /tmp/lipy-darwin-local-client
lab darwin setup
lab darwin start
```

Flags worth knowing:

- `--notebook <name>` — override the default notebook filename
  (default: the project id). Use this when you want parallel notebooks
  in the same project (e.g. `--notebook experiment-a`).
- `--label <name>` — run in an ephemeral kernel, destroyed after the
  run. Use for a one-off query that shouldn't touch the persistent
  session's state.
- `--timeout <sec>` — execution timeout (default 600).
- `lab darwin run-local` — local ipykernel, no pod. Useful for testing
  notebook plumbing without consuming pod resources.

Kernel + proxy state lives in `.darwin.json` (sibling of `project.json`,
gitignored) — `kernel_id` and `proxy_user` are reused across `lab darwin
run` invocations so follow-up questions hit the same interpreter and
can see earlier variables.

**Workflow for "run this analysis":**

1. Ensure the proxy is up: `lab darwin status` (if not, `lab darwin
   start`).
2. `cd knowledge/projects/<project-id>`.
3. `lab darwin run '<code>'` — cells append to
   `notebooks/<project-id>.ipynb`.
4. Open the project in the UI; click the notebook in the sidebar to
   watch cells arrive. No refresh needed.

### Server control

```
lab start                     # `make start-bg` (server on :3333)
lab stop                      # `make stop`
lab open                      # open http://localhost:3333/api/index
```

---

## Server HTTP + WS API (localhost:3333)

### SPA shell
- `GET /`                                 → main UI (gdiff-absorbed)
- `GET /?project=<abs path>`              → per-project view
- `GET /?view=cerebro[&path=rel]`         → Cerebro (knowledge browser)
- `GET /p/{id}`                           → 307 → `/?project=<abs path>`
- `GET /view?path=knowledge/...`          → standalone markdown render

### Reads
- `GET /api/ping`
- `GET /api/index`
- `GET /api/projects[?status=...]`
- `GET /api/projects/{id}`
- `GET /api/projects/{id}/tasks`
- `GET /api/projects/{id}/docs`
- `GET /api/projects/{id}/file?path=...`
- `GET /api/tasks[?status=open&priority=P0,P1&tag=...&label=...]`
- `GET /api/tasks/due?days=N`
- `GET /api/markdown?path=knowledge/...`
- `GET /api/search?q=...`
- `GET /api/cerebro/tree[?include_hidden=true]`
- gdiff-absorbed:
  - `/api/diff?repo=...&type=uncommitted|branch`
  - `/api/commits?repo=...`
  - `/api/commit-diff?repo=...&sha=...`
  - `/api/tree?repo=...`
  - `/api/repos`
  - `/api/project-info?path=...`
  - `/api/project-actions?path=...`
  - `/api/project-onepager?path=...`
  - `/api/project-files?path=...`
  - `/api/project-file?path=...&file=...`
  - `/api/project-mtime?path=...`
  - `/api/project-alerts?path=...`
  - `/api/project-artifacts?path=...`
  - `/api/project-comments?path=...`

### Writes (thin HTTP shell over `lab`)
- `POST /api/projects`
- `POST /api/tasks`
- `POST /api/tasks/{project_id}/{task_id}/status`
- `POST /api/tasks/{project_id}/{task_id}/update`
- `POST /api/projects/{project_id}/prs`                  · `DELETE …/prs/{idx}`
- `POST /api/projects/{project_id}/artifacts`            · `DELETE …/artifacts/{idx}`
- `PUT  /api/project-info`
- `PUT  /api/project-file`
- `POST /api/project-comments`                           · `DELETE /api/project-comments`
- `POST /api/project-action-complete`

### Terminal sessions (tmux + PTY)
- `GET  /api/term/sessions[?project_id=...]`
- `GET  /api/term/sessions/saved?project_id=...`
- `GET  /api/term/projects-with-sessions`
- `POST /api/term/sessions`    body: `{project_id, kind: "claude"|"terminal",
                                       name?, auto?, start_fresh?}`
- `DELETE /api/term/sessions/{name}[?purge=true]`
- `DELETE /api/term/sessions/project/{project_id}[?purge=true]`
- `WS    /ws/term/{name}`      JSON envelope: `{input, data}`,
                                `{resize, rows, cols}`, `{detach}`
- WS `/ws`                     → `{type: "index-updated", ts}` broadcasts

### UI preferences
- `GET  /api/ui/tab-order`
- `POST /api/ui/tab-order`    body: `{order: [pid, ...]}`

The `__cerebro__` pseudo-project behaves like a regular project — same
`/api/term/*` calls, cwd is `knowledge/`, metadata lives in
`knowledge/.cerebro-project.json`.

---

## Web UI cheat sheet

- **Home** — dashboard (project grid, due-this-week, new-project button), timeline, search. Cerebro is pinned here.
- **Project tabs** — top of page. Drag to reorder (persisted server-side via `/api/ui/tab-order`). `+` opens the picker. X kills every tmux session for that project (Claude conversations stay saved; reopen `--resume`s).
- **Terminal panel** — right-docked when a project is loaded. "+ New" picks Claude (auto mode, UUID-tracked) or Terminal ($SHELL). The 📋 copies `tmux attach -t <name> -r` for read-only follow-along in iTerm. X kills the session (tmux session kept around only until the UUID is purged).
- **Cerebro** — Obsidian-style tree of the whole `knowledge/` dir, including every project's docs. `?view=cerebro&path=wikis/...` deep-links.

---

## Conventions

- IDs are slug-y: lowercase letters, digits, `-`. Validated by `lab`.
- Dates ISO (`YYYY-MM-DD`) everywhere.
- Priority: `P0 > P1 > P2 > P3`.
- Status: `active, paused, done, archived` (projects) · `todo, in_progress, blocked, done` (tasks).
- Tags = free-form. Labels = MP slugs (short-name) for cross-linking.
- One-pager at `docs/one-pager.md`. Notes under `notes/`. Assets under `assets/`.
- Worktrees never nest under `docs/`/`notes/`/`assets/`.
