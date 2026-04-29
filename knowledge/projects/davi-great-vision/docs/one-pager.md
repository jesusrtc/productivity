## DAVI -- Tested Automation for Trust Investigations

*Autonomous modules that perform investigation tasks and return hypotheses -- for humans and agents alike.*

**Owner:** Jesus Talamantes | **Team:** Trust IM -- Detection Engineering | **April 2026**

---

### Problem

- Investigation logic lives in local notebooks and markdown files that are not tested, not version-controlled, and not reproducible. When an analyst or agent needs the same logic, they recreate it from scratch -- often differently.
- Markdown skill files tell an LLM what to do but cannot guarantee it does it correctly. There is no test suite, no error tracking, no way to know when the logic breaks.
- As the organization scales investigations (more alerts, more agents, more teams), untested logic becomes a liability -- inconsistent results, silent failures, duplicated effort.

---

### What Exists Today

DAVI is already in production. This is not a proposal -- it is the next chapter of working software.

**15 Darwin widgets** powering Trust IM investigations (InVizor, AlertPlot, DIHE, MagicPlot, and others). InVizor alone saved 40+ hours on single scraping reviews. Each widget saves 30-120 minutes per investigation.

**13 CLI services** exposing DAVI to agents: query execution, SEV calculation, anomaly detection, investigation reports, alert integration. Session management with mandatory audit trails -- every run requires a name, purpose, and recorded findings before proceeding.

**Claude Code integration** via `davi setup claude` -- generates skill files so any Claude Code project can call DAVI services immediately.

**Deployed** via GULL to all LinkedIn machines.

---

### Scope

**DAVI is:** A library of autonomous, tested modules. Each module takes structured input, runs deterministic code, and returns a result or hypothesis. Modules are callable by humans (Darwin) and agents (Claude Code, any CLI consumer). The framework handles testing, session management, audit trails, and error tracking.

**DAVI is not:** An investigation orchestrator, a UI, or a chat interface. DAVI does not decide what to investigate or in what order. It executes the steps -- reliably, reproducibly, and with the same guarantees regardless of who calls it.

---

### Why Now

Investigators are shifting from Darwin notebooks to Claude Code and AI agents for investigations. DAVI widgets already work in Darwin, and DAVI CLI already works with Claude Code locally. The next step is making DAVI modules available to any Claude Code session or agent without requiring a local install, local Trino credentials, or a local Python environment. At the same time, as the module library grows and more teams depend on it, the maintenance problem -- keeping modules working as data changes underneath them -- becomes the critical long-term challenge.

---

### Roadmap

**Now** -- what is working today
- 15 Darwin widgets in production use
- 13 CLI services with Claude Code integration
- SevCalculatorService implementing the SEV framework
- Deployed to all LinkedIn machines via GULL
- Session management, audit trails, and telemetry

**Next (H2 FY26)** -- DAVI modules available to any agent
- DAVI modules callable from any Claude Code session or agent platform without local setup
- Module contribution guide and templates for cross-team contributions
- AI-assisted module creation: analyst describes logic, AI generates code, human reviews and merges
- Target: 5 modules contributed by teams outside core DAVI

```
How it works:

  Agent / Claude Code         DAVI                          Data Layer
  session anywhere      -->   Module execution        -->   Trino / HDFS
  (no local install)    <--   (authenticated, tested) <--
                              Returns: hypothesis / result
```

**Later (FY27)** -- maintenance at scale
- Error telemetry that detects when a module starts failing (schema changes, unexpected inputs, stale data)
- Automated alerts to module owners with context on what broke
- SLAs on resolution -- broken modules get fixed, not forgotten
- Integration tests that run continuously against live data, not just at merge time
- Goal: a module written today still returns a correct hypothesis six months from now

---

### Success Metrics

| Metric | Signal |
| ------ | ------ |
| Adoption | Number of Claude Code projects and agents calling DAVI modules |
| Speed | Time saved per investigation (baseline: 30-120 min per module) |
| Quality | Module pass rate -- % of runs that return a valid result without error |
| Growth | New modules contributed per quarter, including cross-team |

---

### Risks

- **Module reliability.** If a module encodes wrong logic or breaks silently, every consumer gets the wrong answer consistently. Mitigated by tests, code review, and the Phase 3 telemetry investment.
- **Adoption friction.** Teams may prefer ad-hoc queries over structured DAVI calls if the overhead feels too high. Mitigated by AI-assisted creation and zero-config setup (`davi setup claude`).
- **Maintenance debt.** Without the telemetry and SLA infrastructure, module quality degrades over time as upstream data changes. This is the most important long-term investment.

---

### Ask

- Alignment on the direction: DAVI as the tested module library for all investigation platforms
- Support for making DAVI modules available to Claude Code sessions without local setup (H2 FY26)
- Feedback on priorities and phasing
