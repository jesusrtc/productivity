# What the user actually asked for

Single-source-of-truth for the productivity-suite refactor. Written after the
user flagged that the implementation-in-pieces approach missed the point. This
document supersedes the plan-by-plan decomposition in `docs/superpowers/plans/`
as the definition of "done".

---

## 1. The vision (1 paragraph)

Consolidate every productivity piece the user has today (`cerebro`, `apps`,
`darwin-backups`, `trustim-investigation`, `trustim-ir-cli`, `~/projects/*`)
into a single monorepo under `~/src/productivity/`. Replace ad-hoc scripts
with a unified CLI (`lab`) and a web UI (backend + frontend on `:3333`) that
lets the user run their entire day from one place: capture tasks, write docs,
start investigations, edit code via worktrees, render markdown, browse
dashboards. The monorepo should arrive **populated with the user's existing
content**, not as an empty shell.

---

## 2. End-state deliverable (the checklist that defines "done")

### A. Content lives in the monorepo

- [x] `content/projects/<id>/project.json + tasks.json + docs/ + notes/ + assets/`
- [ ] All legacy cerebro content migrated into `content/`:
  - [ ] `content/meetings/` ← from `cerebro/meetings/`
  - [ ] `content/wikis/` ← from `cerebro/wikis/`
  - [ ] `content/roadmaps/` ← from `cerebro/roadmaps/`
  - [ ] `content/logs/` ← from `cerebro/logs/`
  - [ ] `content/skills/` ← from `cerebro/skills/`
  - [ ] `content/im_weekly_update/` ← from `cerebro/im_weekly_update/`
  - [ ] `content/templates/` ← from `cerebro/templates/` (if relevant)
- [ ] All 14 projects under `~/projects/*` migrated into `content/projects/*`,
  each with a proper `project.json` + `tasks.json` converted from the old
  `actions.json` + one-pager/investigation docs preserved + worktrees re-linked:
  - [ ] alerting-migration
  - [ ] davi-great-vision
  - [ ] davi-trino-perf
  - [ ] investigation-jss-feed
  - [ ] investigation-registration
  - [ ] investigations-increase-reg-captcha
  - [ ] oncall-April-26
  - [ ] oncall-drop-signups
  - [ ] oncall-reaction-4xx
  - [ ] project-2B
  - [ ] research-sev-calculator-backtesting-analysis
  - [ ] sev-calculator
  - [ ] trustim-sentinel
  - [ ] (skip `test/` — it's a scratch folder)

### B. Tools live in the monorepo

- [ ] `apps/darwin-runner/` ← from `trustim-investigation/tools/davi_runner.py` (CLI)
- [ ] `apps/darwin-backups/` ← from `productivity-old/darwin-backups/` (notebook store + `q` query CLI)
- [ ] `apps/trustim-ir-cli/` ← from `productivity-old/trustim-ir-cli/` (inResponse CLI)
- [ ] `apps/trustim-investigation/` ← reference skills/templates folder moved in (gitignored if large)
- [ ] `~/.local/bin/` symlinks for each: `darwin-runner`, `darwin-backups`, `trustim-ir-cli`
- [ ] All three CLIs runnable from anywhere on PATH

### C. Repositories + worktrees

- [ ] `repositories/` folder under monorepo root, gitignored
- [ ] `repositories.list` declares which repos the monorepo cares about
  (`lipy-davi`, `im_playbooks`, `abuse-scoring-rules`, `abuse-short-term-action`, ...)
- [ ] `make pull-repos` does `mint clone` for missing repos + `git pull master` for present ones
- [ ] `lab project add <name> <mp>` creates a git worktree at
  `content/projects/<name>/<prefix>-<objective>/` on branch `jcortes/<objective>`
- [ ] `lab project remove <name> <mp>` cleans up the worktree
- [ ] MP→prefix map configured: `lipy-davi→davi`, `abuse-scoring-rules→drools`,
  `abuse-short-term-action→asta`, `im_playbooks→im`, extensible via `lab repo prefix`

### D. CLI — `lab` (already in Plan 1–3, list here for completeness)

- [x] `lab project new|ls|status|set|archive|rm`
- [x] `lab task new|ls|show|set|done|reopen|block|unblock`
- [x] `lab index rebuild|show`
- [x] `lab start|stop|open`
- [ ] `lab project add|remove` (worktrees — §C)
- [ ] `lab mp ls|prefix` (MP prefix management — §C)
- [ ] `lab search "keyword"` (full-text across projects/tasks/docs)
- [ ] `lab pr add <url> [--project <id>] [--mp <mp>]`
- [ ] `lab artifact add <url> [--project <id>] [--type ...]`
- [ ] `lab note <task-id>` (opens notes file, creating if missing)
- [ ] `lab migrate <source-path>` (one-shot ingestor used by the §A migration)

### E. Backend — HTTP + WS (already in Plan 2–3, list for completeness)

- [x] `GET /api/index | /api/projects | /api/projects/{id} | /api/projects/{id}/tasks | /api/tasks | /api/tasks/due | /api/markdown | /api/projects/{id}/docs | /api/projects/{id}/file`
- [x] `POST /api/projects | /api/tasks | /api/tasks/{p}/{t}/status | /api/tasks/{p}/{t}/update`
- [x] `WS /ws` (index-updated broadcasts)
- [x] Watchdog-based live index rebuild
- [x] CORS + static + Jinja shell at `/`
- [ ] `GET /api/search?q=...` (§D `lab search`)
- [ ] `GET /api/diff?project=<id>&mp=<mp>` (diff view of worktrees vs master — folds gdiff in)
- [ ] `GET /api/commits?project=<id>&mp=<mp>` (commit list per worktree)

### F. Frontend — SPA on `:3333/`

- [x] Dashboard: project grid + due-soon strip + status filter
- [x] Project view: Tasks tab + Docs tab
- [x] Timeline: List (bucketed) + Gantt sub-views
- [x] Markdown viewer
- [x] WS live refresh
- [ ] **Replace `prompt()` dialogs with an inline form modal** (new project / new task)
- [ ] **Docs tab: render `.md` as links to markdown viewer, other files as links to `/api/projects/{id}/file`** (currently broken for non-md)
- [ ] **Due strip excludes `status == "done"` tasks** (currently bug: done tasks with past due dates still show)
- [ ] **Keyboard + ARIA**: cards, tabs, pills, Gantt bars focusable and keyboard-activatable
- [ ] **WS auto-reconnect** with exponential backoff
- [ ] Search view at `/search` (§D/E)
- [ ] Diff tab on project view (§E)
- [ ] Artifacts tab on project view (`lab artifact add` surface)
- [ ] Inline task field editing (click priority/due chip to edit without leaving the page)
- [ ] Loading states / spinners for each view fetch

### G. Shared agents + skills (invoked by Claude working in the monorepo)

- [ ] `.claude/agents/intake-processor.md` ← copied from `apps/project/project.sh` agent block
- [ ] `.claude/agents/query-reference.md` ← same source
- [ ] `.claude/agents/migration-agent.md` ← new; drives the §A migration
- [ ] `content/skills/investigation/` ← structured investigation template (funnel, IOC, data approach, tools)
- [ ] `content/skills/one-pager/` ← one-pager template
- [ ] `content/skills/weekly-update/` ← the existing cerebro weekly-update skill
- [ ] Root `CLAUDE.md` points at these agents + skills so a fresh session in the monorepo knows what's available

### H. Claude integration

- [x] Root `CLAUDE.md` tells Claude to use `lab` for everything
- [x] Per-project `CLAUDE.md` auto-generated on `project new`
- [ ] `~/.claude/rules/` symlinks/copies to the monorepo's versions (pre-commit rules, captain rules) so every Claude session in any dir gets the right guidance
- [ ] Optional `PostToolUse` hook example in `.claude/settings.json` showing how to auto-log `git commit` SHAs into `project.json.prs[]`

### I. Install + everyday workflow

- [x] `make install` creates venvs, symlinks `lab` and `lab-backend` onto PATH
- [x] `make start-bg` / `make stop` / `make test`
- [ ] `make pull-repos` works (needs §C)
- [ ] `make seed` creates 2–3 sample projects for demos / new installs (optional)
- [ ] `~/.local/bin` is confirmed on PATH in the user's shell init

---

## 3. Gap analysis — where we are now (2026-04-17)

| Section | Status |
|---|---|
| A. Content migrated in | **0/21 items done**. Monorepo is empty. All content still in `~/src/productivity-old/` and `~/projects/`. |
| B. Tools in monorepo | **0/5 done**. darwin-runner, darwin-backups, trustim-ir-cli, trustim-investigation all still live in `~/src/productivity-old/`. |
| C. Repositories + worktrees | **0/6 done**. No `repositories/` folder, no `make pull-repos`, no `lab project add`. |
| D. CLI | **Core done; advanced missing.** Project/task/index/service commands ship. Worktree, search, PR, artifact, note, migrate commands missing. |
| E. Backend | **Reads + writes done; search + diff missing.** |
| F. Frontend | **Four views shipped with known UX bugs + missing search/diff/artifacts/inline-edit.** |
| G. Agents + skills | **0/6 done**. Templates exist in `productivity-old/trustim-investigation/` but not copied in; no `.claude/agents/` populated. |
| H. Claude integration | **Partially done.** Root CLAUDE.md + per-project CLAUDE.md exist. No `~/.claude/rules/` link-in, no example hook. |
| I. Install + workflow | **Mostly done.** `make pull-repos` missing, `make seed` missing. |

**Net: ~35–40% of the end-state delivered.** The skeleton works; the content + tools + worktree capability + polish are still owed.

---

## 4. Immediate next steps (single push, no review ceremony)

Ordered by user-value-per-minute:

1. **Content migration** (§A) — copy cerebro/* into content/*, run a migration sweep on the 13 keeper projects under `~/projects/*`. After this step the user can actually use the monorepo with their real data instead of a blank dashboard.
2. **Frontend polish** (§F bullets) — inline form modal for new project/new task, fix the docs tab for non-md files, filter done tasks out of the due strip, wire WS auto-reconnect.
3. **Worktree commands** (§C + §D) — `lab project add/remove`, MP prefix config, `make pull-repos`. Enables coding work against lipy-davi / abuse-scoring-rules / abuse-short-term-action.
4. **Tool apps migration** (§B) — move darwin-runner, darwin-backups, trustim-ir-cli into `apps/`, add symlinks, verify they still run.
5. **Shared agents + skills** (§G) — copy the intake-processor / query-reference agents in, scaffold investigation + one-pager skill folders.
6. **Search** (§D + §E + §F) — `lab search`, `/api/search`, `/search` view. Grep-based first, smarter later.
7. **Diff view** (§E + §F) — fold gdiff per-worktree diffs into `/api/diff` + a tab on the project view.
8. **Artifacts + PR tracking UI** (§D + §F) — CRUD forms for the already-existing `artifacts` / `prs` arrays in `project.json`.
9. **Claude rules symlink + example hook** (§H).
10. **`make seed`** (§I — optional, leave for last or skip).

Stop points where the suite is usable enough to ship:
- After **#1 + #2**: user has a populated, polished system for non-coding work.
- After **#1 + #2 + #3**: user can also do coding work via worktrees.
- After **#1–#7**: feature-complete v1.

---

## 5. What this doc changes about how we work

- **No more per-task implementer + spec-reviewer + code-reviewer cycles.** One agent per section, self-verifies with pytest.
- **No more greenfield rewrites.** When the user has existing content, migrate it — don't ask them to re-create it.
- **Each push lands multiple checkboxes from §2.** Progress is measured against that checklist, not against task-card completion.
- **The user can read this doc and see, at a glance, what's done and what's owed.** That transparency is what was missing before.
