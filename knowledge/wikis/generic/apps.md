---
title: "Productivity Apps"
date: 2026-04-03
type: wiki
scope: generic
projects: []
tags: [apps, gdiff, mdview, dashboard, iterm]
sources: []
---

# Productivity Apps

Collection of local tools and web UIs for development workflow.

## Location

`~/src/productivity/apps`

## Structure

```
apps/
├── Makefile          — make install (symlinks), make start (all servers)
├── iterm/
│   └── style.sh      — Shared iTerm2 styling (icon, tab color, tab title)
├── gdiff/
│   ├── gdiff.sh      — CLI: opens browser to git diff viewer
│   ├── server.py     — FastAPI web viewer (port 3333)
│   ├── diff_parser.py — Git diff parsing
│   └── templates/
├── mdview/
│   ├── mdview.sh     — CLI: opens browser to markdown viewer
│   ├── server.py     — FastAPI markdown renderer (port 3334)
│   └── templates/
├── dashboard/
│   ├── server.py     — Port dashboard (port 80)
│   └── templates/
└── docs/
```

## Commands

- `make install` — symlinks `gdiff`, `mdview`, `style.sh` to `~/.local/bin` and `~/.local/share/cerebro`
- `make start` — runs all servers (dashboard:80, gdiff:3333, mdview:3334), Ctrl+C stops all
- `gdiff` — from any git repo, opens diff viewer in Edge (per-folder tab reuse)
- `mdview` — from any folder, opens markdown viewer in Edge (per-folder tab reuse)

## Key Features

- **gdiff**: GitHub-style diff viewer, uncommitted/branch diffs, commit history, live reload, notebook support
- **mdview**: Obsidian-style markdown viewer, YAML frontmatter badges, live reload via WebSocket, time filters (Today/This Week/Last Week)
- **dashboard**: Port scanner showing running services
- **style.sh**: Shared project detection for iTerm2 tab colors/icons, sourced by .zshrc, Claude statusline, and gdiff

## Roadmap

See `roadmaps/productivity-apps.md` (in cerebro)
