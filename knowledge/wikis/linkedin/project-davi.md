---
title: "Project: DAVI"
date: 2026-04-02
type: wiki
scope: org
projects: [davi]
tags: [project-overview, platform, cli, abuse-detection, investigations]
people: [jcortes, hezus]
sources: ["https://docs.google.com/document/d/1d2FdnWwOER3Uc_ejcAzbWvNUAAZpw5GCy4D795dMkNo/edit?tab=t.v7xgz532k92x"]
---

# DAVI Platform

**Source**: [DAVI CLI Google Doc](https://docs.google.com/document/d/1d2FdnWwOER3Uc_ejcAzbWvNUAAZpw5GCy4D795dMkNo/edit?tab=t.v7xgz532k92x)
**Repo**: lipy-davi

## What It Is

DAVI is a platform for abuse investigations at LinkedIn. It evolved from a collection of Jupyter widgets (Darwin interactive tools) into a three-tier service platform that any execution context — human or AI agent — can call.

## Why It Evolved

- LLM agents were improvising logic from widget source code instead of using tested services
- Markdown instructions (CLAUDE.md) couldn't enforce agent behavior — code can
- No telemetry or error tracking when widgets failed silently

## Architecture (Three Tiers)

### Layer 1: Clients
- **Darwin**: Jupyter Widgets (legacy/human)
- **DAVI CLI**: AI agents and scripts

### Layer 2: Service Layer
Plain Python classes, client calls `.run()` and gets a `ServiceResult`.

**Core Services (9 shipped):**
- QueryService — Trino queries
- DataFrameService — data manipulation
- MagicPlotService — chart generation
- AlertPlotService — alert visualization
- SevCalculatorService — quantify abuse impact (SEV determination)
- ReportService — HTML report assembly
- EmailService — email delivery
- IntakeService — record IOCs
- InvestigationReportService — investigation reports

**Supporting:**
- Render functions (e.g., `magic_plot_render`)
- Context management (`read_context()` / `write_context()`)
- Telemetry — logs to Trino (`u_davi.errors`, `u_davi.feedback`), migrating to Kafka

### Layer 3: Context (State)
Persistent session storage on disk, 1:1 with an investigation.
- `context.json` — shared key-value state (title, severity, status, IOCs)
- Artifacts — typed outputs per run (`.parquet`, `.png`, `.json`, `.html`, `.md`)
- Cross-run references (e.g., `run-02:output:dataframe`)

### External
- **DAVI Viewer** (`localhost:3284`) — read-only Flask UI for sessions/runs/charts/reports

## Investigation Workflow

Strict, deterministic flow enforced on agents:
1. `davi session create` — empty context
2. `davi run IntakeService` — record IOCs
3. **Note enforcement** — agent must `davi note run-XX` to unblock next step
4. Query & analysis cycles (QueryService, MagicPlotService, etc.)
5. Error handling via `davi introspect` + `davi feedback`
6. `davi run ReportService` — assemble HTML report
7. State recovery: `davi session attach` restores full history

## Key Concepts

- **DIHE**: Daily Impacted Hostile Entities
- **SEV Calculator**: Quantifies abuse impact for cohorts that don't hit top-line thresholds
- **Cohort**: A group of member IDs sharing an abuse pattern
- **Data egress**: Volume of data scraped/exfiltrated
- **Services vs Skills**: Skills describe what an agent *should* do; services enforce what it *must* do

## Dev Setup

```bash
mint clone lipy-davi
cd lipy-davi
git checkout jcortes/overall-improvements  # temp branch for final version
./install-dev.sh

cd path/some/claude/project
davi init
davi setup claude
```

## Components Living in DAVI

- SEV Calculator (SevCalculatorService)
- Scraping alerts
- Investigation workflow engine
- DAVI Viewer (local web UI)
