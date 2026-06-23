# Unify backend — one process, gdiff as the base

> Working doc. Decisions captured here; when a question has an answer, update the bullet and move on.

---

## Today (2 processes, 2 ports)

| Piece | Port | What it serves |
|---|---|---|
| `lab-backend` (FastAPI) | **3333** | `/` SPA shell · `/api/index` · `/api/projects[...]` · `/api/tasks[...]` · `/api/markdown` · `/api/search` · POST mutation routes · WS `/ws` |
| `gdiff` (FastAPI) | **3334** | `/?project=<abs path>` → rich project track UI · `/api/project-info` · `/api/project-actions` (reads `tasks.json`) · `/api/project-onepager` · diff viewer · commit list · notebook rendering |
| `lab` (CLI only) | — | `project/task/mp/pr/artifact/search/index/start/stop` — entry point for all writes |

The UI feels split because clicking a project from the dashboard (:3333) opens a new tab on :3334. Back button and nav don't bridge the two.

---

## Target (1 process, 1 port)

**Start from gdiff.** Its UI is the one you want everywhere. Bring the read-only APIs + WS + search + dashboard from `lab-backend` into gdiff's FastAPI app. Drop `lab-backend` as a separate process. `lab` CLI stays as-is (it's the write path).

Result:
- One `uvicorn` process (one venv, one Makefile target: `make start`)
- One port (:3333)
- One URL base
- `lab` CLI unchanged — web is a convenience over it

---

## Decisions to make (answer inline; I'll start once §A–§E are filled)

### §A. Frontend shell — which HTML/JS drives the UI?

- **A1.** Keep gdiff's existing `templates/index.html` (2530 lines, the rich layout) as the shell. Dashboard becomes a new "home" mode inside the same HTML, styled to match.
- **A2.** Keep the SPA module-router (`#/`, `#/p/<id>`, `#/timeline`, …) and mount gdiff's project view as the content of `#/p/<id>`.
- **A3.** Hybrid: gdiff's visual language (sidebar + main panel) at every route, but each route owns its own template fragment.

My pick: **A1**. Reason: you said "la UI de gdiff no cambie mucho, es funcional". A2 means forking gdiff's HTML into pieces; A1 lets its existing layout absorb the dashboard + timeline + search.

Your answer: `_____`

### §B. Which gdiff features stay?

Check the ones you want preserved (default: all):

- [ ] File tree + diff viewer (uncommitted / vs master / commits)
- [ ] Action items sidebar (powered by new `tasks.json`)
- [ ] One-pager rendering (markdown panel)
- [ ] Commit list + per-commit diff
- [ ] Notebook (.ipynb) rendering
- [ ] Pinned files at top of sidebar
- [ ] Comments (ephemeral markup-via-UI for Claude to consume)
- [ ] Alerts panel

Anything you'd drop: `_____`

### §C. Which `lab-backend` features come into the unified backend?

- [ ] `/api/index` + watcher + WS `/ws` (live dashboard refresh)
- [ ] `/api/markdown` (generic md viewer — gdiff already renders md for one-pagers, check if there's duplication)
- [ ] `/api/search` + `/search` view (grep across content/)
- [ ] POST mutation routes (`/api/projects`, `/api/tasks`, `/api/tasks/{p}/{t}/status`, `/api/projects/{p}/prs`, `/api/projects/{p}/artifacts`)
- [ ] Dashboard view (project grid + due-this-week strip)
- [ ] Timeline view (list bucketed by due + Gantt)
- [ ] Cross-project `/api/tasks` flat list
- [ ] CORS middleware (only needed if you ever run a dev frontend on another port; skip if no)

Anything you'd drop: `_____`

### §D. URL structure inside the unified backend

- **D1.** Keep gdiff's `GET /?project=<abs path>`. Pro: no breakage for existing gdiff muscle memory. Con: URLs are long.
- **D2.** Migrate to `GET /p/<id>` (SPA style). Pro: clean. Con: every gdiff JS call that reads `?project=` needs to change.
- **D3.** Support both; `?project=` is the source of truth, `/p/<id>` is a redirect.

My pick: **D3** — smallest change + clean URLs work.

Your answer: `_____`

### §E. `lab` CLI — stays, but how does backend invoke it for POST writes?

- **E1.** Subprocess per request (current). Works but slow (~200 ms Python boot per call) + blocks event loop.
- **E2.** Extract lab's write logic into an importable `lab.ops` module; backend calls Python functions directly. `lab` CLI keeps the same behavior, just becomes a thin wrapper.

My pick: **E2** eventually, but **E1 is fine for now** — the UI has no heavy-write flows yet. Postpone until slowness is felt.

Your answer: `_____`

---

## Once §A–§E are answered — next steps

(Order assumes **A1 / D3 / E1 (defer)** + all gdiff features kept + all lab-backend read routes absorbed. If you pick different, the order may shift.)

### Phase 1 — merge backends (1 process, 1 port)

1. Create `apps/server/` (or rename `apps/backend/` → `apps/server/`) as the single FastAPI app. Starting point: copy gdiff's `server.py` in.
2. Add `lab` as an editable dep to `apps/server/pyproject.toml` (already the pattern). Add `watchdog`, `markdown`, `pyyaml`, `jinja2` on top of gdiff's existing fastapi/uvicorn.
3. Mount the existing routers from current `apps/backend/src/backend/routes/` (index, project, task, markdown, search, mutation, ws) into the gdiff-based app.
4. Move the index cache + watcher lifecycle (`apps/backend/src/backend/main.py::lifespan`) into the unified app.
5. Port everything to :3333. Drop :3334. Update `make start` to be single-target; remove `start-all`.
6. Update `~/.local/bin/` symlinks — `lab-backend` goes away, `gdiff` becomes an alias for the unified backend (or just drop it, `lab start` is enough).
7. Run both test suites. Fix any imports that moved.

### Phase 2 — merge frontends

8. Make `templates/index.html` (gdiff's) the served shell at `/`.
9. Add a "Home" / "Dashboard" mode to gdiff's HTML: show the project grid + due-this-week strip using the same sidebar+main layout.
10. Add a "Timeline" mode (list + Gantt). Same HTML, new panel content.
11. Add a "Search" mode.
12. Preserve gdiff's per-project view untouched — when `?project=<path>` or `/p/<id>` matches, render it as today.
13. WS-based live refresh: when `index-updated` arrives, refresh only the currently visible panel (dashboard grid or project actions list).

### Phase 3 — data-side cleanup

14. Unify `/api/markdown` vs gdiff's one-pager reader. One renderer, two callers.
15. Ensure `/api/search` covers everything (code in worktrees? just content/?).
16. Single CORS policy (probably none — same-origin only).

### Phase 4 — polish

17. Replace `prompt()` modal flows where they still exist.
18. Inline task-field edit (click priority chip → edit).
19. Search pagination.
20. Keyboard shortcuts across the shell (j/k to navigate project cards, `/` to focus search, etc.).

---

## What stays out of this effort

- Separate personal/client CLIs do not belong in the framework repo's `apps/` tree. `apps/` is now reserved for workspace-owned apps created inside a Lab workspace; framework code lives under `core/` and `core/cli/`.
- `repositories/` + `make pull-repos` — works as-is.
- `lab` CLI subcommands — no surface change.
- Existing migrated content under `content/` — untouched.

---

## Open questions for you

These are the 5 I need answered before starting Phase 1:

1. **§A** — A1, A2, or A3?
2. **§B** — any gdiff features to drop?
3. **§C** — any lab-backend features to drop?
4. **§D** — D1, D2, or D3?
5. **§E** — E1 (keep subprocess for now) or E2 (extract lab.ops now)?

Reply in whatever form — inline edits to this doc, or just "A1, keep all gdiff, drop timeline from lab, D3, E1-for-now" works.
