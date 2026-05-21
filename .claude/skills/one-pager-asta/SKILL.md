---
name: one-pager-asta
description: >-
  Draft an ASTA (anti-abuse short-term action) one-pager covering rule
  design: Background (for revamps), Executive Summary, abusive behavior,
  job config, key metrics with coverage chart, ramp schedule, detection
  logic, detection SQL, monitoring SQL, and tests. Use when the user
  wants to write up an ASTA rule design or revamp, often after an
  investigation identified the pattern to detect. Triggers: "ASTA
  one-pager", "write up the {rule} ASTA", "design doc for {rule}",
  "ASTA rule design".
---

# ASTA one-pager

Output goes to `content/projects/<id>/docs/one-pager.md`. **Never publish
to Google Docs.** Local file only.

Often follows an investigation one-pager when the investigation
justifies a new or revamped rule.

## Ask first (single message, then wait)

Before writing, ask the user these in one message and wait for answers:

1. Is this a **new rule** or a **revamp / improvement** of an existing one? If revamp: old name + link to the prior one-pager.
2. What's the new rule name (Scala class / TRex namespace / model name)?
3. What's the abuse pattern in one sentence? (Link the investigation one-pager if there is one.)
4. What's the impact / lift? (Candidate counts, net-new restrictable members, cohort coverage %.)
5. What's the precision per surface? (Or overall, if single surface.)
6. What's the action + label? (e.g. `TAZER_LOGIN_RESTRICT` + `FAKE`.)
7. Cadence + windows? (bihourly / daily, stats window, candidate window.)
8. Ramp shape? (e.g. Day 1 10% → Day 3 50% → Day 7 100%.)
9. Where do the simulation notebook + Trino query live?
10. PR / Jira link if open already.

## Output skeleton

```markdown
# <Rule name> (<new|rename + expansion of OldName>)

**Status:** Draft | **Date:** YYYY-MM-DD | **Owner:** <name> | **Jira:** <ticket>

## Background  *(only when this is a revamp/improvement)*
<Current behavior of the existing rule (what it detects today, which
surfaces, thresholds) and the gap it faced (what's missing, what abuse
it lets through). Link the prior one-pager.>

## Executive Summary
<What we're changing in one sentence + simulation numbers + net-new lift
+ cohort coverage. For new rules (no Background), this is the only
top-level summary.>

## Identified abusive account behavior
<Describe the pattern + what makes the identity abusive (handle? device?
sequence?). Be precise about which signals fire on which surface. This
section is about WHAT the abuser does.>

## Job Name and Action
- Scala class: ...
- Cleanup-subjob name: ...
- TRex namespace: ...
- Model name: ...
- Action: ... + label ...
- Schedule / stats window / candidate window: ...

## Key Metrics
<Per-surface table: candidates, restricted-within-14d, precision %.>
<Net-new actionable from production-shape query.>

![Rule coverage over time](assets/<slug>_coverage_over_time.png)

<Same chart shape as the investigation signature chart: x = date,
color = "Would be restricted by this rule" vs "Other", y = count.
Visually answers "how much of the spike does this rule explain /
cover?". Built via the davi-investigations skill.>

## Ramp Schedule
- Day 1 (YYYY-MM-DD) — X%
- Day N (YYYY-MM-DD) — Y%
- Day M (YYYY-MM-DD) — 100%

## Next Steps
- [WIP|Pending] <action> — <owner>

## Logic
<Narrative of detection method. Regex / signal definition / threshold.
This is distinct from "Identified abusive account behavior" — Behavior
describes WHAT the abuser does; Logic describes HOW we detect it.>

## SQL — Detection (production-shape)
<The query the Scala rule runs. Last few days. Returns list of member
IDs to act on.>

​```sql
<Detection query.>
​```

## SQL — Monitoring (coverage chart)
<Time-series query that powers the chart above. Returns three columns
(day, label, count). Same regex / predicate as detection, but
backfilled across the spike window so the chart shows the
"would-restrict" cohort against the rest. Hand the result to
davi.plot() — see the davi-investigations skill.>

​```sql
<Monitoring query — outputs (day, label, count) for davi plot.>
​```

## Tests
- <Test case> — <expected behavior>

## Related Links
- Source code: ...
- Investigation: ...
- Prior one-pager (revamp predecessor): ...
- Simulation notebook (local): ...
```

## Rules

- **Keep both** "Identified abusive account behavior" AND "Logic" —
  Behavior first (what the abuser does), then Logic (how we detect it).
- **Include Background only when it's a revamp/improvement** of an
  existing rule. For new rules, jump straight to Executive Summary.
- **Both Detection SQL and Monitoring SQL are required.** Detection
  returns a member-ID list for the last few days; Monitoring returns
  `(day, label, count)` time-series for the coverage chart, backfilled
  across the spike window.
- **The coverage chart embed is required.** Build via
  `davi-investigations`. PNG goes at
  `assets/<slug>_coverage_over_time.png`.
- No Google Docs publishing. Ever.
