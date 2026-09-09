# Productivity Monorepo — Design Spec

**Date:** 2026-04-16
**Status:** Draft — pending user review
**Codename:** `lab`

---

## 1. Overview

Today the user's productivity setup is spread across five folders under `~/src/productivity/` (cerebro, apps, darwin-backups, trustim-investigation, trustim-ir-cli), plus a working area at `~/workspaces/` and canonical MP checkouts at `~/src/multiproducts/`. Markdown is rendered by two different stacks (gdiff's `marked.js` and mdview's Python `markdown` library). Tasks live nowhere coherent — `cerebro/todos/` is empty, `DASHBOARD.md` is hand-edited, per-workspace `actions.json` exists only inside `~/workspaces/<name>/`. Closing a terminal tab loses research context. Cerebro doesn't see working-area changes unless `workspace sync` is run manually.

This spec replaces that layout with a single git monorepo at `~/src/productivity/` that owns:

- **Content** — knowledge (meetings, wikis, roadmaps, logs) and workspaces (with tasks, docs, notes, worktrees)
- **Tools** — CLIs and web services (the unified `lab` CLI, one web backend, one frontend, plus darwin-runner / darwin-backups / trustim-ir-cli as apps)
- **MP clones** — gitignored `multiproducts/` populated from scratch by `make pull-repos`

A single CLI named **`lab`** is the only sanctioned write path for workspace/task state. A single web service on one port serves the dashboard, workspace views, a roadmap/Gantt, a list view, and markdown rendering for anything under `content/`. Tasks are JSON (no frontmatter). A watcher rebuilds a global `.index.json` on change.

## 2. Goals

- **One physical home** for content, tools, and workspace state. Monorepo, one `.git`, one `Makefile`, one root CLAUDE.md.
- **One CLI** (`lab`) subsumes the existing `workspace` CLI, adds task commands, owns the global index, wraps search.
- **One web service** with one backend and one frontend — multiple routes (dashboard, workspace view, timeline, list, md). gdiff and mdview get folded in (now or soon).
- **JSON as the source of truth** for workspace/task state. No YAML frontmatter. Markdown is human-authored content attached to tasks or docs.
- **Agent-driven archetypes, not labeled types.** A workspace can start as investigation and end as a one-pager. Tools are globally available; the agent chooses.
- **Dashboard filters by `status`**, no separate `tracked` flag.
- **Zero schema enforcement in prose.** `lab` validates every write, so CLAUDE.md only needs to say "use `lab`".

## 3. Non-goals

- Multi-user or shared workspaces.
- Time tracking. (LOE is an estimate, not a log.)
- Mobile access.
- Preserving git history of the five absorbed repos. Data moves; git log resets at migration time.
- Moving `~/src/multiproducts/`. The monorepo's `multiproducts/` is built from scratch via `mint clone`; the user's existing `~/src/multiproducts/` is untouched and can coexist.
- The port-80 port-scanner dashboard, `tm`, and `iterm/style.sh`. These stay where they are (or get removed separately).
- Cross-conversation Claude session resurrection beyond what Claude Code natively supports. If a session is lost, it's lost.

## 4. Physical layout

```
~/src/productivity/                     ← the monorepo
├── .git/
├── .gitignore                          (multiproducts/, .index.json, __pycache__, venv, .DS_Store)
├── CLAUDE.md                           (root instructions — short, points to lab)
├── Makefile                            (install, start, pull-repos)
├── README.md
├── .claude/
│   └── agents/                         (shared: intake-processor, query-reference, migration-agent)
├── apps/
│   ├── lab/                            (the unified CLI — Python)
│   │   ├── lab                         (entrypoint script)
│   │   ├── pyproject.toml
│   │   ├── src/lab/
│   │   │   ├── cli.py
│   │   │   ├── commands/
│   │   │   │   ├── workspace.py
│   │   │   │   ├── task.py
│   │   │   │   ├── index.py
│   │   │   │   ├── search.py
│   │   │   │   ├── mp.py               (mp alias / prefix management)
│   │   │   │   └── dashboard.py        (start/stop service)
│   │   │   ├── model.py                (workspace/task dataclasses, validation)
│   │   │   ├── storage.py              (atomic json read/write)
│   │   │   └── paths.py                (monorepo root detection)
│   │   ├── config/
│   │   │   └── mp-prefixes.json        (MP → short prefix map)
│   │   └── tests/
│   ├── backend/                        (FastAPI web service, port 3333)
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── workspace.py
│   │   │   ├── task.py
│   │   │   ├── index.py
│   │   │   ├── markdown.py             (mdview logic merged in)
│   │   │   ├── diff.py                 (gdiff logic merged in — see §7)
│   │   │   └── search.py
│   │   ├── watcher.py                  (watchdog → rebuild .index.json)
│   │   ├── renderer.py                 (shared markdown → HTML)
│   │   └── requirements.txt
│   ├── frontend/                       (single HTML/JS app)
│   │   ├── index.html
│   │   ├── static/
│   │   └── templates/
│   ├── darwin-runner/                  (was trustim-investigation/tools/davi_runner.py)
│   │   ├── darwin-runner              (CLI)
│   │   └── src/
│   ├── darwin-backups/                 (clones of past notebooks, plus `q` query CLI)
│   │   ├── darwin-backups             (CLI entry: download, q, ls)
│   │   ├── downloads/                  (gitignored — bulk notebook dumps)
│   │   └── src/
│   ├── trustim-ir-cli/                 (moved in, existing CLI structure preserved)
│   │   └── ...
│   ├── gdiff/                          (kept until merged into backend — see §7)
│   └── mdview/                         (kept until merged into backend — see §7)
├── multiproducts/                      ← GITIGNORED
│   ├── lipy-davi/                      (master branch, refreshed by `make pull-repos`)
│   ├── im_playbooks/
│   ├── abuse-scoring-rules/
│   └── ...                             (any MP listed in multiproducts.list)
├── multiproducts.list                  (plain text, one MP name per line, checked in)
└── content/
    ├── workspaces/
    │   ├── inbox/                      (catch-all for standalone reminders)
    │   │   ├── workspace.json
    │   │   └── tasks.json
    │   ├── davi-great-vision/
    │   │   ├── workspace.json
    │   │   ├── tasks.json
    │   │   ├── docs/
    │   │   │   ├── one-pager.md
    │   │   │   └── vision.md
    │   │   ├── notes/
    │   │   │   └── 002-review-prep.md
    │   │   ├── assets/
    │   │   │   └── chart.png
    │   │   ├── davi-great-vision/      (worktree, lipy-davi → branch jcortes/great-vision)
    │   │   └── im-great-vision/        (worktree, im_playbooks → branch jcortes/great-vision)
    │   └── ...
    ├── meetings/
    │   └── 2026-04-02-sev-refinement.md
    ├── wikis/
    │   ├── linkedin/
    │   └── personal/
    ├── roadmaps/
    ├── logs/
    │   ├── linkedin/
    │   └── personal/
    ├── skills/                         (shared templates + skills)
    │   ├── investigation/              (investigation.md template, IOC pattern, data approach)
    │   ├── one-pager/
    │   ├── weekly-update/
    │   └── README.md
    └── .index.json                     ← GITIGNORED, rebuilt by watcher
```

### What's different from today

| Today | Monorepo |
|---|---|
| 5 git repos under `~/src/productivity/` | 1 monorepo |
| `~/workspaces/<n>/` is the working area | `content/workspaces/<n>/` is the working area |
| `~/src/multiproducts/` (canonical) | `multiproducts/` inside monorepo (gitignored, rebuilt via mint) |
| `workspace` CLI (bash, 36KB) | `lab` CLI (Python, modular) — absorbs workspace commands |
| gdiff :3333, mdview :3334, port-80 dashboard | backend :3333 serving everything; port-80 dashboard stays separate |
| Per-workspace `actions.json`, no cross-workspace view | `tasks.json` per workspace + global `.index.json` aggregating all |
| `cerebro/todos/` empty | `content/workspaces/inbox/tasks.json` for loose reminders |
| YAML frontmatter in cerebro md files (optional) | JSON state, markdown is content only |
| `tm`, `iterm/style.sh` | out of monorepo (stay where they are) |

## 5. Data model

### 5.1 `workspace.json`

```json
{
  "id": "davi-great-vision",
  "name": "DAVI Great Vision",
  "description": "Reshape DAVI from Darwin widget library to deterministic execution layer for Trust investigations.",
  "status": "active",
  "tags": ["davi", "vision"],
  "labels": ["lipy-davi", "im_playbooks"],
  "priority": "P1",
  "loe": 15,
  "due": "2026-05-01",
  "created": "2026-04-15",
  "updated": "2026-04-16",
  "worktrees": [
    {"mp": "lipy-davi", "dir": "davi-great-vision", "branch": "jcortes/great-vision"},
    {"mp": "im_playbooks", "dir": "im-great-vision", "branch": "jcortes/great-vision"}
  ],
  "prs": [
    {"url": "https://...", "mp": "lipy-davi", "title": "Add deterministic executor", "status": "open"}
  ],
  "artifacts": [
    {"type": "google_doc", "url": "https://...", "title": "Vision deck", "description": "Leadership review draft"}
  ],
  "pinned": ["docs/vision.md", "docs/one-pager.md"]
}
```

**Field reference:**

- `id` — folder name; kebab-case; starts with an MP prefix when possible. **Immutable** after creation.
- `status` — one of `active | paused | done | archived`. Dashboard default filter = `active`. `archived` hides from everything.
- `tags` — free-form user-picked tokens. Searchable.
- `labels` — MP names (autocompleted from `multiproducts/`). Different from `tags`: labels are typed against the MP list.
- `priority` — `P0 | P1 | P2 | P3` (P0 = drop everything; P3 = nice to have). Optional at workspace level.
- `loe` — numeric days (`0.5`, `1`, `2`, `5`, `13`). Optional at workspace level.
- `due` — ISO date. Optional.
- `worktrees` — array derived from `lab workspace add`. Each entry has the MP, the folder name inside the workspace, and the branch.
- `prs` — array; updated by `lab pr add` (manual) or an optional hook.
- `artifacts` — external references (same shape as today's `artifacts.json`, folded into `workspace.json`).
- `pinned` — relative paths to files the dashboard highlights at the top of the workspace view.

### 5.2 `tasks.json`

```json
{
  "next_id": 5,
  "tasks": [
    {
      "id": 2,
      "title": "Review one-pager with Jesus",
      "status": "in_progress",
      "priority": "P1",
      "loe": 0.5,
      "due": "2026-04-20",
      "tags": ["review"],
      "labels": [],
      "blocker": null,
      "notes_file": "notes/002-review-prep.md",
      "created": "2026-04-15",
      "updated": "2026-04-16",
      "closed_at": null
    },
    {
      "id": 3,
      "title": "Circulate to reviewers",
      "status": "todo",
      "priority": "P2",
      "loe": 0.5,
      "due": "2026-04-22",
      "tags": [],
      "labels": [],
      "blocker": null,
      "notes_file": null,
      "created": "2026-04-15",
      "updated": "2026-04-15",
      "closed_at": null
    }
  ]
}
```

**Field reference:**

- `id` — integer, unique per workspace. Not globally unique. `next_id` is auto-incremented by `lab`.
- `status` — one of `todo | in_progress | blocked | done`. Only `done` sets `closed_at`.
- `priority` — `P0 | P1 | P2 | P3`. Required.
- `loe` — days, numeric. Optional.
- `due` — ISO date. Optional.
- `tags` — free-form.
- `labels` — MP names. Auto-inherited from workspace unless overridden.
- `blocker` — string describing the blocker. Set when `status = blocked`. Cleared on unblock.
- `notes_file` — relative path (`notes/<id>-<slug>.md`) if the task has notes. Nullable.
- `created` / `updated` / `closed_at` — ISO timestamps.

### 5.3 Task state machine

```
              ┌──────────────────┐
              │                  ▼
 [todo] → [in_progress] → [done]
    │          ▲      ▲
    │          │      │
    └──→ [blocked] ───┘
```

- `todo → in_progress`: any time
- `todo → blocked`, `in_progress → blocked`: `lab task block <id> "reason"` sets blocker
- `blocked → in_progress | todo`: `lab task unblock <id>` clears blocker
- `* → done`: `lab task done <id>` sets `status: done`, `closed_at: <now>`
- `done → *` is allowed (reopen) — clears `closed_at`

### 5.4 Global index (`content/.index.json`)

Regenerated by the backend's watcher on any change under `content/`. Not committed.

```json
{
  "generated_at": "2026-04-16T17:00:00-07:00",
  "workspaces": [
    {
      "id": "davi-great-vision",
      "status": "active",
      "tags": ["davi", "vision"],
      "labels": ["lipy-davi", "im_playbooks"],
      "priority": "P1",
      "due": "2026-05-01",
      "earliest_task_due": "2026-04-20",
      "open_task_count": 2,
      "blocked_task_count": 0,
      "path": "content/workspaces/davi-great-vision"
    }
  ],
  "tasks": [
    {
      "workspace_id": "davi-great-vision",
      "task_id": 2,
      "title": "Review one-pager with Jesus",
      "status": "in_progress",
      "priority": "P1",
      "due": "2026-04-20",
      "tags": ["review"],
      "labels": [],
      "path": "content/workspaces/davi-great-vision/tasks.json#2"
    }
  ]
}
```

The index is a *cache*. The web frontend reads only `.index.json`. Drilling into a workspace view reads the individual `workspace.json` and `tasks.json`. This keeps home-view renders O(1).

## 6. The `lab` CLI

### 6.1 Command surface

```
# Workspace lifecycle
lab workspace new <id> [--desc "..."] [--labels lipy-davi,...] [--priority P1] [--due 2026-05-01]
lab workspace ls [--status active|paused|done|archived] [--tag ...] [--label ...]
lab workspace status [<id>]                        # defaults to PWD's workspace
lab workspace set <id> <field> <value>             # e.g. status=done, description="..."
lab workspace archive <id>                         # status=archived (hides from default dashboard)
lab workspace rm <id>                              # hard delete — asks confirmation, removes worktrees, deletes folder
lab workspace add <id> <mp> [--branch <name>]      # creates worktree (see §9 for naming)
lab workspace remove <id> <mp>                     # removes a worktree

# Task lifecycle
lab task new "title" [--workspace <id>] [--file] [--priority P1] [--loe 2] [--due 2026-04-20] [--tags ...] [--labels ...]
lab task done <id> [--workspace <id>]
lab task block <id> "reason" [--workspace <id>]
lab task unblock <id> [--workspace <id>]
lab task reopen <id> [--workspace <id>]
lab task set <id> <field> <value> [--workspace <id>]
lab task mv <task-id> --to <workspace-id>          # reparent a task
lab task rm <id>                                 # hard delete (rare)
lab task ls [--workspace <id>] [--status open|done] [--due 7d] [--tag ...] [--priority P0,P1]
lab task show <id> [--workspace <id>]              # prints JSON + notes file

# Cross-cutting
lab search "keyword" [--in workspaces|tasks|docs|all]
lab index rebuild                                # one-shot; normally the watcher handles it
lab mp ls                                        # lists MPs in multiproducts/ and prefix mapping
lab mp prefix <mp> <prefix>                      # e.g. lab mp prefix lipy-davi davi

# Web service
lab start                                        # = make start (alias)
lab stop
lab open                                         # opens http://localhost:3333 in browser

# Misc
lab pr add <url> [--workspace <id>] [--mp <mp>] [--title "..."]
lab artifact add <url> [--workspace <id>] [--type google_doc|jira|...] [--desc "..."]
lab note <task-id> [--workspace <id>]              # opens notes file (creates if missing, scaffolds header)
```

### 6.2 Behavior notes

- **PWD detection.** When `lab` is invoked inside a workspace folder (even a worktree subdir), the CLI walks up to find `workspace.json` and auto-fills `--workspace`. Outside a workspace, `--workspace` is required for task commands.
- **Atomic writes.** All state writes go through `storage.py` which writes to a temp file and renames (no torn writes).
- **Validation.** Every write goes through `model.py` dataclasses — wrong status, unknown priority, malformed date all fail with a clear error.
- **ID assignment.** `tasks.json.next_id` is the authoritative counter. `lab task new` reads, bumps, writes. Race-free for a single-user system.
- **Slugging.** Task filename slug is generated from the title (lowercased, non-alnum → `-`, truncated). Never changed after creation.
- **Notes file.** `--file` on `lab task new` creates `notes/<id>-<slug>.md` with a header. Without `--file`, `notes_file` stays null. `lab note <id>` creates the file lazily on first open.
- **Dry-run.** Every mutating command supports `--dry-run` printing the intended change.

### 6.3 The root CLAUDE.md (single source of guidance)

```markdown
# Productivity monorepo

You're in a single-user productivity monorepo. Everything you need lives here.

## How to do anything

Use `lab`. Run `lab --help` for commands. Never hand-edit `workspace.json`, `tasks.json`, or `.index.json`.

## Where things live

- `content/workspaces/<id>/` — active workspaces (one folder each)
- `content/meetings|wikis|roadmaps|logs/` — knowledge that isn't workspace-scoped
- `content/skills/` — shared templates (investigation, one-pager, weekly-update)
- `apps/` — CLIs and the web service (`lab`, `darwin-runner`, `darwin-backups`, `trustim-ir-cli`, `backend`, `frontend`)
- `multiproducts/` — gitignored MP clones on master. Refresh with `make pull-repos`.
- `.claude/agents/` — shared agents: `intake-processor`, `query-reference`, `migration-agent`

## On workspace work

When you're in `content/workspaces/<id>/`, read that workspace's CLAUDE.md too.

## Archetypes (no types)

Workspaces are not labeled. If the user asks you to investigate, draft from `content/skills/investigation/` and use the tools in `apps/`. If they ask for a one-pager, use `content/skills/one-pager/`. Pick based on the ask.
```

### 6.4 Per-workspace CLAUDE.md (auto-generated on `lab workspace new`)

```markdown
# <workspace.name>

## Objective
<workspace.description — or empty, ask on first session>

## On session start
Run `lab workspace status` for current state.
Check the Dashboard at http://localhost:3333/p/<id> if web service is running.

## Task operations
Use `lab task ...` for all changes. Current tasks: `lab task ls`.

## Available tools
- `apps/darwin-runner` — matplotlib charts on Darwin kernel
- `apps/darwin-backups q "…"` — query past notebooks for examples
- `apps/trustim-ir-cli` — inResponse queries

Agents at the repo root `.claude/agents/`.
Templates at `content/skills/`.
```

## 7. Backend service

Single FastAPI on port 3333.

### 7.1 Routes

```
GET  /                          index.html (single-page app)
GET  /api/workspaces              list (from .index.json; optional ?status=active)
GET  /api/workspaces/{id}         workspace.json content
GET  /api/workspaces/{id}/tasks   tasks.json content
GET  /api/workspaces/{id}/docs    list of md files under docs/ and notes/
GET  /api/workspaces/{id}/file    raw file (text or binary, path param)
GET  /api/tasks                 all tasks (from index; filtered by query params)
GET  /api/tasks/due?days=N      upcoming-due
GET  /api/markdown              render any md under content/ (path param → {frontmatter, html})
GET  /api/diff                  merged diff for a workspace's worktrees (absorbed from gdiff)
GET  /api/diff/notebook         notebook-specific diff (from gdiff)
GET  /api/commits               (from gdiff)
GET  /api/search                fulltext
GET  /api/index                 the raw index

POST /api/workspaces              (proxies to `lab workspace new` — optional; CLI is primary)
POST /api/tasks                 (proxies to `lab task new`)
POST /api/tasks/{workspace}/{id}/status  (proxies to `lab task set`)

WS   /ws                        broadcasts {"type": "index-updated", "ts": ...}
                                    whenever watcher rebuilds the index
```

The web UI can also invoke `lab` via `POST`-style routes, but the primary write path is still the CLI. The reason: hooks, scripts, and the user's own terminal commands all go through the CLI. The web POSTs are a convenience for mouse-driven edits (e.g. marking a task done by clicking a checkbox).

### 7.2 Watcher

Uses `watchdog.Observer` in a startup background thread.

- Watches `content/**/workspace.json`, `content/**/tasks.json`, `content/**/*.md` (for search)
- On any event: `lab index rebuild` in-process (not via subprocess)
- Broadcasts `{type: "index-updated"}` over the WS so connected frontends refresh
- Debounces rapid bursts (250ms)

### 7.3 gdiff + mdview merge path

Today's `apps/gdiff/` and `apps/mdview/` keep running on their current ports through M1 (see §11). In M2, their server code moves into `apps/backend/routes/diff.py` and `routes/markdown.py`; their templates become components in the new frontend; the old folders are removed. Rendering logic:

- **Markdown rendering is server-side** (Python `markdown` library, same as today's mdview) — returned as HTML via `GET /api/markdown`. The frontend no longer uses `marked.js`. One renderer, one feature set, one place to extend.
- Notebook rendering (current in gdiff templates) becomes a backend route returning structured JSON the frontend renders.

## 8. Frontend

Single-page app at `apps/frontend/`. Plain HTML + vanilla JS or a tiny framework — whatever existing gdiff/mdview templates use, kept simple.

### 8.1 Views (tabs, Airtable-style)

```
┌─────────────────────────────────────────────────────────────────┐
│ [Dashboard] [Timeline] [List] [Search]            Open: lab CLI │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Dashboard view content…                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Dashboard (`/`)**

- Top strip: "Due this week" — tasks across all workspaces, by date, colored by priority.
- Below: grid of workspace cards (filterable by status, default `active`). Each card shows:
  - name + description (1 line)
  - task bar: `todo: 3 · in_progress: 1 · blocked: 0 · done: 2` (click to filter workspace view)
  - earliest due
  - priority + LOE + `due` (if set at workspace level)
  - tags + labels as chips
- Click a card → workspace view.

**Workspace view (`/p/<id>`)**

- Header: workspace name, description, status, priority, due, tags, labels.
- Left rail: nav of docs (from `docs/`), notes (from `notes/`), assets. Pinned files on top.
- Center: active tab — one of:
  - `tasks` (default) — grouped by status columns (like a static kanban but without drag)
  - `docs` — rendered md selected from left rail
  - `diff` — git diff viewer for worktrees (replaces gdiff per-workspace view)
  - `artifacts` — external links
- Right rail: PRs list, artifacts quick links.

**Timeline view (`/timeline`)**

Airtable-style with two sub-views toggled by pill:

- **Gantt** — rows = workspaces, bars from `created` (or task's earliest `created`) to `due`, major tasks rendered as dots along the bar. Horizontal scroll by month/quarter.
- **List** — flat list of all tasks across workspaces, sorted by `due`, grouped into "This week", "Next week", "This month", "Later", "No due". Each row: workspace name, task title, status, priority chip.

**Search view (`/search`)**

- Full-text search across workspaces/tasks/docs. Results grouped by type. Click-through navigates to workspace/task/doc.

### 8.2 No kanban view in v1

Deferred. The workspace view's task columns are static and cover the primary use case.

### 8.3 Live updates

All views open a WebSocket to `/ws`. On `index-updated`, refresh the current view from the API. No polling.

## 9. Worktree + branch naming

### 9.1 MP prefix table (seed, extendable)

`apps/lab/config/mp-prefixes.json`:

```json
{
  "lipy-davi": "davi",
  "abuse-scoring-rules": "drools",
  "abuse-short-term-action": "asta",
  "im_playbooks": "im"
}
```

Extend via `lab mp prefix <mp> <prefix>`.

### 9.2 Rules

- **Workspace id** (folder name) SHOULD start with a known MP prefix + hyphen + objective: `davi-great-vision`, `drools-rate-limit`, `asta-spike-april-26`. When it doesn't (e.g., `inbox`, `research-sev-calc`), the workspace is still valid — only worktree naming is affected (see below).
- **Objective extraction.** If the workspace id starts with a known prefix followed by `-`, `objective = id[len(prefix)+1:]`. Otherwise `objective = id`.
- **`lab workspace add <workspace> <mp>`:**
  - Reads the MP's prefix from the table (error if unknown; user must add a mapping).
  - Worktree folder = `<mp_prefix>-<objective>`. For the primary MP whose prefix matches the workspace, this equals the workspace id itself (e.g., workspace `davi-great-vision` + MP `lipy-davi` → folder `davi-great-vision`, which is the workspace name — cute and clear).
  - Branch = `jcortes/<objective>`. All worktrees in the same workspace share the branch name.
  - Worktree path: `content/workspaces/<workspace>/<mp_prefix>-<objective>/`
- **`--branch <name>`** overrides the computed branch if needed.

### 9.3 Examples

| Workspace id | MP added | Worktree path | Branch |
|---|---|---|---|
| `davi-great-vision` | `lipy-davi` | `content/workspaces/davi-great-vision/davi-great-vision/` | `jcortes/great-vision` |
| `davi-great-vision` | `im_playbooks` | `content/workspaces/davi-great-vision/im-great-vision/` | `jcortes/great-vision` |
| `drools-rate-limit` | `abuse-scoring-rules` | `content/workspaces/drools-rate-limit/drools-rate-limit/` | `jcortes/rate-limit` |
| `asta-spike-april-26` | `abuse-short-term-action` | `content/workspaces/asta-spike-april-26/asta-spike-april-26/` | `jcortes/spike-april-26` |
| `oncall-drop-signups` | `lipy-davi` | `content/workspaces/oncall-drop-signups/davi-oncall-drop-signups/` | `jcortes/oncall-drop-signups` |

The last case: workspace id doesn't start with a known prefix, so `objective = workspace id` itself. The `davi-` prefix is still added to the worktree folder to keep MP affiliation obvious.

## 10. Tool apps (CLIs moved into `apps/`)

### 10.1 `apps/darwin-runner/`

Former `trustim-investigation/tools/davi_runner.py`. Converted to a proper app with its own entrypoint:

```
darwin-runner run-local --notebook <name> --workspace <id>    # matplotlib charts
darwin-runner run-remote --notebook <name>                  # runs on Darwin kernel
darwin-runner ls                                             # list available notebooks
```

### 10.2 `apps/darwin-backups/`

Current `darwin-backups` download scripts + new `q` subcommand:

```
darwin-backups download [--all | --user jcortes]             # bulk fetch
darwin-backups ls [--pattern "*spike*"]                      # list local notebooks
darwin-backups q "how did they plot T7D with overlay?"       # semantic search over downloaded notebooks
```

`q` can start as naive grep over notebook sources and become smarter later (embeddings) — kept as an implementation detail.

### 10.3 `apps/trustim-ir-cli/`

Moved in unchanged. Entry at `apps/trustim-ir-cli/trustim-ir-cli`.

### 10.4 Install / PATH

`make install` symlinks every CLI entry point into `~/.local/bin/`:

```
lab
darwin-runner
darwin-backups
trustim-ir-cli
```

## 11. Makefile

```makefile
.PHONY: install uninstall start stop pull-repos seed

BIN_DIR := $(HOME)/.local/bin

install:
	@pip install -e apps/lab
	@pip install -r apps/backend/requirements.txt
	@ln -sf $(CURDIR)/apps/lab/lab $(BIN_DIR)/lab
	@ln -sf $(CURDIR)/apps/darwin-runner/darwin-runner $(BIN_DIR)/darwin-runner
	@ln -sf $(CURDIR)/apps/darwin-backups/darwin-backups $(BIN_DIR)/darwin-backups
	@ln -sf $(CURDIR)/apps/trustim-ir-cli/trustim-ir-cli $(BIN_DIR)/trustim-ir-cli
	@echo "Installed. Run 'make pull-repos' then 'make start'."

uninstall:
	@rm -f $(BIN_DIR)/lab $(BIN_DIR)/darwin-runner $(BIN_DIR)/darwin-backups $(BIN_DIR)/trustim-ir-cli

pull-repos:
	@mkdir -p multiproducts
	@while read mp; do \
	  [ -z "$$mp" ] && continue; \
	  if [ ! -d multiproducts/$$mp ]; then \
	    echo "cloning $$mp..."; \
	    (cd multiproducts && mint clone $$mp); \
	  fi; \
	  echo "updating $$mp (master)..."; \
	  (cd multiproducts/$$mp && git checkout master && git pull --quiet); \
	done < multiproducts.list

start:
	@cd apps/backend && uvicorn main:app --host 0.0.0.0 --port 3333 --reload

stop:
	@pkill -f "uvicorn main:app --port 3333" || true

seed:
	@python apps/lab/scripts/seed-test-workspaces.py
```

- `make install` once after clone
- `make pull-repos` any time; idempotent
- `make start` replaces the three `uvicorn` invocations from today's `apps/Makefile`
- `make seed` creates the sample workspaces in §14

## 12. Hooks & Claude integration

### 12.1 Where to start Claude

- **Monorepo root** for meta work: workspace creation, cross-workspace queries, knowledge curation, meetings/wikis/logs maintenance.
- **Inside a workspace folder** for workspace-specific work. Root CLAUDE.md is still discoverable (CLAUDE.md chain).
- Either way, `lab` is on PATH and works.

### 12.2 Hook recommendations

`~/src/productivity/.claude/settings.json` (checked in, minimal):

```json
{
  "hooks": {
    "PostToolUse": []
  }
}
```

Empty by default. The implementation phase will flesh out concrete hook config using Claude Code's current `hooks` schema (`matcher`, `type`, `command`). Two hooks are worth considering, both opt-in:

- **Auto-index after `lab` write commands.** Watcher already catches file changes; this is belt-and-braces. Matches `Bash` tool calls where the command starts with `lab task ` or `lab workspace `, then runs `lab index rebuild`.
- **Auto-append commit SHA to workspace.json.** Useful for PR tracking. Matches `Bash` tool calls where the command starts with `git commit`, then runs `lab pr track-commit --from-pwd` which detects the PWD's workspace and appends the latest commit's SHA + message.

Final hook syntax follows Claude Code's `hooks` config schema verified against the active version at implementation time. Both are off by default; user enables per preference.

### 12.3 Shared agents

`.claude/agents/` at the monorepo root. These are available from any workspace without per-workspace copies.

- `intake-processor.md` — unchanged from today's `workspace` investigation scaffolding
- `query-reference.md` — unchanged
- `migration-agent.md` — new; used by `make migrate` (§14) to ingest existing `~/workspaces/<n>/` folders

## 13. Bootstrap flow (first run, new machine)

```bash
git clone <monorepo> ~/src/productivity
cd ~/src/productivity
make install             # installs lab, darwin-runner, etc. into ~/.local/bin
make pull-repos          # mint clone each MP in multiproducts.list, git pull master
make start               # starts backend on :3333
lab open                 # opens http://localhost:3333
```

First-run checks inside `lab`:
- Validates `~/.local/bin` is on PATH
- Validates `mint` is installed
- Validates `multiproducts.list` exists (prompts to create if missing)

## 14. Migration plan

Two separate migrations, in order.

### 14.1 Seed the monorepo structure

1. Create new git repo at `~/src/productivity-new/` (scratch location). Initialize with `.gitignore`, `Makefile`, `CLAUDE.md`, empty `apps/`, `content/`, `docs/`.
2. Copy `apps/lab/` code (new — written in impl phase).
3. Copy `apps/backend/` code (new — incorporates gdiff + mdview merged).
4. Copy `apps/frontend/` (new).
5. Copy `apps/gdiff/`, `apps/mdview/` from current `apps/` as-is — these remain available through M1 and are deleted when the merged backend ships.
6. Move `trustim-investigation/tools/davi_runner.py` → `apps/darwin-runner/`.
7. Move `darwin-backups/` → `apps/darwin-backups/`.
8. Move `trustim-ir-cli/` → `apps/trustim-ir-cli/`.
9. Move `cerebro/meetings|wikis|roadmaps|logs|skills/` → `content/`.
10. Move `cerebro/DASHBOARD.md` → `content/archive/DASHBOARD-pre-monorepo.md` (content superseded by the live dashboard view but kept for reference).
11. Write `multiproducts.list` from current `~/src/multiproducts/` folder names (or curate — some might be unused).
12. `make install && make pull-repos && make start`.

Once working, swap directories: `mv ~/src/productivity ~/src/productivity-old && mv ~/src/productivity-new ~/src/productivity`.

### 14.2 Migrate existing `~/workspaces/<n>/` folders

At time of writing, the following exist:

```
~/workspaces/
├── alerting-migration
├── davi-great-vision
├── davi-trino-perf
├── investigation-jss-feed
├── investigation-registration
├── investigations-increase-reg-captcha
├── oncall-April-26
├── oncall-drop-signups
├── oncall-reaction-4xx
├── workspace-2B
├── research-sev-calculator-backtesting-analysis
├── sev-calculator
├── test
└── trustim-sentinel
```

Migration strategy: **one sub-agent per workspace**. For each source workspace, spawn a `migration-agent` with:

```
Input:  source path ~/workspaces/<name>/
Output: content/workspaces/<name>/ in the monorepo
        content/workspaces/<name>/migration-report.md

Steps the agent performs:
1. Read source .workspace.json, actions.json, artifacts.json, comments.json, alerts.json (whatever exists).
2. Read all markdown files (one-pager.md, investigation.md, README.md, intake.md, etc.).
3. Inspect source subfolders; distinguish:
   - worktrees (have .git file pointing at main repo) — moved as worktrees
   - resources/ symlinks — dropped (tools are now global in apps/)
   - assets/ — moved as-is
   - other doc folders — moved into docs/
4. Derive the MP prefix for the workspace name; propose a renaming if the current name doesn't follow the convention. Require user confirmation before renaming.
5. Construct content/workspaces/<name>/workspace.json from the source .workspace.json. Derive:
   - status (if absent, ask)
   - labels from prs[].mp (or repos)
   - description from one-pager.md / README.md first paragraph if absent
6. Construct content/workspaces/<name>/tasks.json from actions.json. Each action becomes a task:
   - status, updated, blocker preserved
   - priority defaulted to P2 if absent (flag for user review)
   - loe and due left empty
7. Move docs:
   - one-pager.md → docs/one-pager.md
   - investigation.md → docs/investigation.md
   - README.md → docs/README.md (if content-bearing)
   - other top-level md → docs/<filename>
8. Move assets/ unchanged.
9. For each worktree: git worktree remove (or git worktree move), then re-create pointing at monorepo's multiproducts/<mp> (this requires the mp to exist in multiproducts/; if not, skip with a warning and let user run make pull-repos + lab workspace add).
10. Write migration-report.md next to the new workspace folder summarizing what was migrated, what was skipped, what needs user follow-up.
```

The `migration-agent.md` definition lives at `.claude/agents/migration-agent.md`. A make target invokes it:

```makefile
migrate-workspaces:
	@for src in $(HOME)/workspaces/*/; do \
	  name=$$(basename $$src); \
	  echo "Migrating $$name..."; \
	  lab migrate --source $$src --name $$name; \
	done
```

`lab migrate` dispatches the sub-agent. User reviews `migration-report.md` for each workspace and deletes the old `~/workspaces/<n>/` once satisfied.

### 14.3 Rollback

Since `~/src/productivity-old/` and `~/workspaces/` are untouched during migration, rollback is `mv ~/src/productivity ~/src/productivity-new-broken && mv ~/src/productivity-old ~/src/productivity` plus restoring zsh PATH entries. No data loss possible.

## 15. Test fixtures

`make seed` creates five test workspaces (real structure, fake content) to exercise the dashboard, timeline, task states, and priorities:

- `inbox` — 3 standalone tasks, one due today, one P0, one blocked.
- `davi-test-vision` — 8 tasks mixing statuses, a notes file attached to two of them, labels `lipy-davi`, one worktree registered (but not actually cloned, since the seed shouldn't require mint).
- `drools-test-spike` — 4 tasks, P0/P1, one blocker, one recently closed with `closed_at` set to verify the "Done" grouping renders correctly.
- `investigation-test-metric-spike` — 5 tasks, 2 docs (`intake.md`, `investigation.md`), a real chart asset, artifacts pointing at fake Retina URLs.
- `doc-test-one-pager` — 1 task, `docs/one-pager.md` with real-looking content.

The seed script uses `lab` itself (no direct JSON writes), proving the CLI covers the full surface.

## 16. Non-obvious design choices

- **Per-workspace `tasks.json` instead of per-task files.** Fewer files, JSON arrays are trivial to diff, task IDs are local to the workspace (no global counter race). The cost is: no single-file task grep; mitigated by the global index + `lab search`.
- **Index is a cache, not the truth.** Deleting `.index.json` is safe — the watcher rebuilds it. This means losing the cache never loses state.
- **`lab` is the write boundary, web UI is read-mostly.** The UI can POST convenience actions, but those just proxy to `lab`. Only one code path validates and writes, which keeps schema enforcement clean.
- **No frontmatter anywhere in `content/`.** All queryable state is JSON. Markdown is content only. Grep for content, `lab` for state.
- **No archetype.** Workspaces are undifferentiated. Archetype-specific templates (investigation funnel, one-pager structure) live in `content/skills/` and are pulled in by Claude on demand.
- **Monorepo's `multiproducts/` is separate from `~/src/multiproducts/`.** Monorepo rebuilds its own from scratch. The user's existing checkouts outside the monorepo are untouched. Some disk is wasted; zero migration risk.

## 17. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Losing a partly-migrated workspace during §14.2 | Source `~/workspaces/<n>/` not touched until user approves migration-report and runs `rm` manually. |
| Watchdog not detecting changes on macOS (APFS quirks) | `watchdog` defaults to `FSEvents` on macOS, known-good. Fallback: polling every 2s. |
| `mint clone` auth failure blocks bootstrap | `make pull-repos` logs per-MP errors and keeps going; missing MPs listed at the end with instructions. |
| Claude hand-editing JSON despite guidance | Pre-commit hook (optional) runs `lab validate` and blocks commits with malformed JSON. |
| Index goes stale if watcher crashes | `lab index rebuild` one-shot; backend endpoint also rebuilds on demand. Dashboard shows `generated_at` timestamp so staleness is visible. |
| Schema evolution (new field added) | `model.py` uses permissive deserialization (unknown fields preserved). `lab migrate-schema` subcommand added as needed. |

## 18. Out of scope (call-outs for future specs)

- **Merging gdiff + mdview into backend** — happens in M2 (post-launch), own spec follows.
- **Embedding-based `darwin-backups q`** — starts as grep, smarter later.
- **Kanban view with drag-and-drop.** Not in v1.
- **Multi-user / shared cerebro.**
- **Mobile web UI.**
- **Auto-archive of `done` workspaces after N days.** Currently manual via `lab workspace archive`.
- **Time tracking per task** (actual hours worked).
- **`tm`, `iterm/style.sh`, port-80 port-scanner dashboard** — left in current locations.

## 19. Implementation milestones (preview)

Rough sequencing; full plan in a separate `writing-plans` pass.

- **M0 — Skeleton** — monorepo layout, `.gitignore`, empty dirs, root CLAUDE.md, Makefile skeleton.
- **M1 — `lab` CLI core** — `workspace` + `task` commands, storage, validation, global index (`lab index rebuild`).
- **M2 — Backend + watcher** — FastAPI, watchdog, `/api/workspaces`, `/api/tasks`, `/api/index`, WS.
- **M3 — Frontend shell** — Dashboard + workspace view + markdown renderer.
- **M4 — Timeline view** — Gantt + list sub-views.
- **M5 — Tool apps migration** — darwin-runner, darwin-backups (with `q` stub), trustim-ir-cli moved in.
- **M6 — Search + artifacts + PR tracking** — cross-cutting features.
- **M7 — Migration** — `migration-agent` and `lab migrate`, applied to existing `~/workspaces/*`.
- **M8 — gdiff/mdview merge** — fold into backend, delete old dirs.
- **M9 — Seed + polish** — `make seed`, docs, README.
