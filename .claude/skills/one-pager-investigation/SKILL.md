---
name: one-pager-investigation
description: >-
  Draft an investigation one-pager that opens with a director-friendly
  narrative TLDR + a signature IoC-over-time chart, then drills into the
  IoC, drill-down levels, audit/behavior, defense gaps, and next steps.
  Use when the user wants to summarize an incident, metric spike, or
  trust/safety investigation for leadership and engineers in one doc.
  Triggers: "investigation one-pager", "write up the {incident}",
  "summarize the {spike}", "incident one-pager".
---

# Investigation one-pager

Output goes to `content/projects/<id>/docs/one-pager.md`. **Never
publish to Google Docs.** Local file only.

## Ask first (single message, then wait)

Before writing, ask the user these in one message and wait for answers:

1. What is the incident or metric? (e.g. "Feed DIHE spike Mar 22-31", "Telesign SMS cost increase Feb 2026")
2. How was it discovered? (alert name, dashboard, manual flag, customer report)
3. What is the status? (active / mitigated / resolved / monitoring)
4. What is the abuse type? (ATO / fake accounts / scraping / payment / unknown / not abuse)
5. What is the impact? (DIHE, restricted accounts, cost, member-facing harm)
6. Do you have IoCs identified? If yes, what defines an IoC for this case? (e.g. "logged in with unfamiliar device AND updated email handle")
7. Where do the supporting analysis + charts live? (notebook path, asset folder)
8. Who is DRI / oncall IM / investigator?

## TLDR style guide (the part directors read)

Tell the story:
**what happened → how/when it was discovered → what we found → root cause (if known)**.

**Generalize patterns. Do NOT cite low-level signals like UA strings, IP
literals, or single MIDs in the TLDR.**

Good — *"They logged in after days of inactivity with no challenge, and
attempted from several email domains, primarily gmail and mail.ru."*

Bad — *"MID 412977836 logged in with UA=AAAAA from IP 1.2.3.4 using gmail."*

Worked example (Telesign cost spike):

> An increase in Telesign SMS costs was detected across multiple regions
> for February 2026 compared to December. Upon triage, Trust IM
> identified that the primary source was registration-specific. Onset
> was a clear step-change around January 5–6, 2026. After further
> investigation, the vast majority of these SMS were delivered in
> unsuccessful registration attempts. The root cause is not an external
> attack but an internal rule change — a new *Dynamic Challenge
> Assignment Rule – Phone* that started ramping in early January and is
> preventing fake-account registrations.

## Signature IoC chart (required, directly under TLDR)

```
![Signature IoC chart](assets/<slug>_ioc_over_time.png)
```

Build it via the `davi-investigations` skill — it owns the 3-column SQL
contract (`time, label, count`) and the `linkedin.davi.plot()` recipe.

## Output skeleton

```markdown
# <Incident name>: Investigation One-Pager

**Status:** Active|Mitigated|Resolved | **Date:** YYYY-MM-DD | **Investigator:** <name>
**Oncall IM:** <name> | **DRI:** <name>

---

## TLDR
<Narrative paragraph(s) for directors. Story style. Generalize patterns.>

![Signature IoC chart](assets/<slug>_ioc_over_time.png)

---

## How it was discovered
<1–2 sentences: alert / dashboard / manual flag + date.>

## What we found (the IoC)
<Define the IoC precisely. Table or short prose. This is the "is_ioc"
predicate used in the chart above.>

## Drill-down
**Level 1 — <dominant dimension> explains <N%> of the increase.** <Evidence.>

**Level 2 — Within <L1>, <sub-dimension>.** <Table with precision / recall / multiplier.>

**Level 3 (optional) — <further refinement>.**

## Audit / Behavior
<Bulleted findings with concrete numbers: challenges shown/solved, IP/UA
patterns, restriction history. Generalize patterns; cite a handful of
MIDs only as illustrative examples.>

## Defense gaps
1. <Gap with concrete data point.>
2. <Gap with concrete data point.>

## Key metrics
| Metric | Value |
|---|---|
| ... | ... |

## Next steps
- <Action — owner — status>

## Datasets
| Table | Purpose |
|---|---|

## References
- <Retina dashboard, related docs, prior incident, SEV thread>
```

## Rules

- **Section order is fixed:** TLDR (with chart) → How discovered → What
  we found → Drill-down → Audit/Behavior → Defense gaps → Key metrics →
  Next steps → Datasets → References.
- Markdown freely — tables, embedded images, bold lead-ins, em-dashes.
- **Embed the signature IoC chart only ONCE**, directly under TLDR.
  Other charts (per-level drill-down, cohort timelines) go inside their
  respective sections.
- Bold lead-in sentence carrying the takeaway, then the evidence.
- Cite MIDs only when illustrating a finding; **never in the TLDR**.
- No Google Docs publishing. Ever.
