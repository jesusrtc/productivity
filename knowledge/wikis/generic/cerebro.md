---
title: "Cerebro"
date: 2026-04-03
type: wiki
scope: generic
projects: [cerebro]
tags: [knowledge-base, productivity]
sources: []
---

# Cerebro

Personal knowledge base for tracking work context, meeting notes, todos, logs, and wikis.

## Location

`~/src/productivity/cerebro`

## Structure

```
cerebro/
├── CLAUDE.md              — Index, conventions, query instructions
├── DASHBOARD.md           — Current focus, weekly goals, project status
├── find.sh                — Search utility (project/tag/person/keyword/scope/etc)
├── meetings/              — Meeting notes with YAML frontmatter
├── wikis/
│   ├── linkedin/          — LinkedIn/org knowledge (tools, projects, systems)
│   └── generic/           — Generic knowledge (tools, how-tos, productivity)
├── logs/
│   ├── linkedin/          — Org work logs
│   └── personal/          — Personal productivity logs
├── todos/                 — Task lists per project
├── roadmaps/              — Future plans per project
└── templates/             — Reusable frontmatter templates
```

## Key Concepts

- **YAML frontmatter** on every file: title, date, type, scope, projects, tags, people
- **Scope**: `personal` (your own productivity) vs `org` (LinkedIn/team work)
- **find.sh**: CLI search by project, tag, person, keyword, scope, type, recency
- **Workflow**: When meeting notes are pasted, Claude proposes a filing plan before writing anything. User approves all changes.

## Roadmap

See `roadmaps/productivity-cerebro.md`
