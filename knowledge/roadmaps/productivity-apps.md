---
title: "Roadmap: Productivity Apps"
date: 2026-04-03
type: roadmap
scope: personal
projects: []
tags: [roadmap, apps, gdiff, mdview, tmux]
---

# Roadmap: Productivity Apps

## 1. gdiff: browser-only like mdview (no terminal subscription)

Remove the terminal fswatch loop from gdiff. The server handles everything — `gdiff` just opens the browser to the right URL (like mdview does now). No subscription, no background process.

## 2. gdiff: consolidated multi-repo view

When running `gdiff` in a parent folder containing multiple repos, show a single page with:
- Combined uncommitted changes across all child repos
- Combined commit history
- Per-repo sections or a unified view with repo labels

Use case: a project folder with 3 repos — see all changes in one place for multi-repo work.

## 3. tm: smart tmux session launcher

A wrapper CLI (`tm`) that:
- Creates/attaches tmux session named after current folder (or arg)
- Sets iTerm tab title + color via passthrough escapes (reuses style.sh)
- Conditional formatting based on project detection (like style.sh)
- Optional layout presets (e.g. 4-pane with claude + processes)
- `tm` with no args: creates session for current folder
- `tm start`: runs the full setup (split panes, launch commands)
- Lives in `apps/tm/tm.sh` → `~/.local/bin/tm`

---

## Priority Order

1. gdiff browser-only (simplify, remove terminal mode complexity)
2. Multi-repo consolidated view in gdiff
3. tm: smart tmux session launcher
