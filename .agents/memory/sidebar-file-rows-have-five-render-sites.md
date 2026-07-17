---
name: sidebar-file-rows-have-five-render-sites
description: File rows are string-built in five separate places in lab-app.js — any change to row markup (icons, badges, decorations) must be applied to all of them
metadata:
  type: project
---

`core/src/core/static/js/lab-app.js` builds file/tree rows in five
independent places. A change to row markup (icons, git decorations,
badges) silently misses surfaces unless applied to every site:

1. Project sidebar files — `_refreshProjectSidebar` (~line 4390)
2. Project sidebar Meta rows (project.json, shared CLAUDE/AGENTS) (~4470)
3. Shared `.claude/`/`code/` async tree — (~8015)
4. Productivity self-view — `selfPopulateSidebar`/`renderSelfTree`
   (~11380); the self view is rooted at `find_framework_root()`, injected
   as `window.LAB_MONOREPO_ROOT`
5. Repo/Project tab tree — `renderTreeNodes` `tree-file` rows (~1454)

Shared icon helper: `fileIconHtml()` (~870). Related: `/api/git-status`
containment allows the active workspace, `get_registered_repos()` paths,
and the framework root (self view) — nothing else.

**Why:** a subagent restyling "the sidebar" hit sites 1–3 and missed 4–5;
the user immediately noticed both.

**How to apply:** grep for `sidebar-fname`, `tree-file`, and `ft-icon`
before declaring a row-markup change complete.
