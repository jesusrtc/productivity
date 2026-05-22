---
name: role-description
description: >-
  Research a LinkedIn role / team / function across internal sources
  (local skill repos, Confluence, JIRA, Jarvis code search, Slack,
  Google Docs) and write either a job description (external-audience,
  hiring) or a CV duties section (external-audience, job-seeker). Use
  when the user asks for a JD, role description, position description,
  CV / resume duties, or "what does an engineer on team X do".
---

# Role description skill

Use when the user wants any of:

- A job description for a role / team / function ("write a JD for a
  Trust IM IR engineer", "draft a position description for a backend
  ML platform engineer on team Y").
- A CV / resume duties section for their own role ("write up my duties
  for my CV", "list my responsibilities for an external audience").
- An exhaustive picture of what someone on a given LinkedIn team
  actually does, day to day.

The two outputs share the same research phase. Run the research once,
then write the artifact the user asked for. If they ask for both,
produce two files.

## Output locations

Save to `content/wikis/linkedin/` because role / team descriptions are
durable LinkedIn-internal reference notes.

- Job description: `content/wikis/linkedin/<slug>-job-description.md`
- CV duties: `content/wikis/linkedin/<slug>-cv-duties.md`

`<slug>` is the role / team slugified, e.g. `trust-im-ir-engineer`.

## Research phase

Run sources in parallel; each one fills a different gap. Trust local
evidence first, then external systems.

1. **Local skill / plugin repos** under
   `/Users/jcortes/src/productivity/repositories/` —
   the team's own investigation / oncall / runbook skills are the
   strongest source for what the team actually does day to day. Read
   the README, the `CLAUDE.md`, and every `SKILL.md` under `skills/`.
2. **Confluence** via `mcp__captain__search_confluence_content` —
   team charters, oncall summaries, onboarding pages, incident
   runbooks. `mcp__captain__get_confluence_page` to pull a specific
   page; the team's weekly oncall summary is usually the canonical
   "what oncall does" doc.
3. **JIRA** via `mcp__captain__search_jira_issues` — sample the team's
   active projects to see the texture of real work: bug tickets,
   feature work, escalations, autoalerts. Look at both the team's
   primary project and any TP&D / threat-prevention / recommendation
   backlog the team owns.
4. **Code** via `mcp__captain__jarvis_codesearch` — pipelines, rules
   files (`.drl`, `.scala`, `.py`), schemas, online services owned by
   the team. This is how you confirm the "ships X" claims.
5. **Google Docs / Slack** via `mcp__captain__search_google_docs_text`
   and `mcp__captain__search_slack` — supplement only. If Slack is
   throttling, do not block; the local + Confluence + JIRA + code
   sources are usually enough.

Skip sources that return nothing useful in one or two queries. Do not
chase noise.

## Job description (external audience, hiring)

Structure:

```
# Job Description — <Role title>

> Short framing: where this draft is grounded.

## Role at a glance
<3-4 sentence narrative framing of the role and team>

## What you will work on
### 1. <Duty bucket 1>
<Narrative + bullets. Cite real systems, real metrics, real example incidents.>
### 2. <Duty bucket 2>
...

## A representative week
<Narrative day-by-day or week-by-week walkthrough — Monday morning the
oncall pager fires, Tuesday you draft an ASTA proposal, etc. This is
the section recruiters and candidates remember.>

## What you will need
### Required
### Strongly preferred
### Helpful but not required

## Stack and tools
<Concrete systems, scoped to the role>

## How the role fits in the org
<Adjacent teams and partnerships>

## What success looks like in the first six months
<3-6 measurable outcomes>
```

Rules:

- Lead with concrete work, not org chart. The first thing the reader
  should see is what they will actually do.
- Cite real systems by name (Trino, Drools, Flink, Spark, Venice,
  Espresso, …). Internal codenames are fine in a JD that targets an
  external candidate who would Google them after applying — they
  signal depth. Briefly describe the system in-line the first time.
- Quantify with real numbers where the evidence supports it (e.g.
  "200+ alert tickets per week", "petabyte-scale Trino", "98%
  precision rule"). Do not invent.
- No tables. The user prefers prose + bullets + code blocks in
  long-form docs.
- No em dashes — use commas, semicolons, or periods.
- Length: 2-4 pages of markdown. Exhaustive when the user asked for
  exhaustive, otherwise compact.

## CV duties (external audience, job-seeker)

Structure:

```
# CV duties — <Role title>, LinkedIn

> Short framing: external-audience, action-led, quantified.

## Headline summary
<1 paragraph for the role overview>

## <Competency area 1>
- Action-led bullet
- Action-led bullet
...

## <Competency area 2>
- Action-led bullet
...

## Stack — for the skills section
<Bulleted system inventory>
```

Rules:

- Past tense, action-led ("Led X", "Built Y", "Investigated Z",
  "Authored", "Shipped", "Designed", "Reduced").
- Translate LinkedIn-internal jargon to industry-readable terms:
  - Drools → "Drools rules engine" (kept; real industry tool)
  - ASTA → "automated batch enforcement jobs"
  - DIHE → "harm metrics"
  - Frame → "feature framework"
  - Venice / Ambry → "online feature stores"
  - Darwin → "managed Jupyter platform"
  - IRIS → "internal alerting system"
  - LIX → "experiment platform"
  - InResponse → "incident management platform"
  - holdem / Trino → "Trino at petabyte scale"
- Quantified anchors are framed as scale-of-work ("authored rules
  catching 500/day at 100% precision in production validation"), not
  sole credit. The user edits credit lines for what they personally
  led.
- Group by competency (investigation / rule authoring / detection /
  data engineering / ML partnership / cross-team / etc.), not by
  project.
- Aim for 8-12 sections, 30-60 bullets total when exhaustive.
- No tables.
- No em dashes.
- Codenames stay only when they read as legitimate technical context
  to a non-LinkedIn reader (Evilginx is a real public phishing kit;
  internal cluster names are not).

## Workflow

1. Confirm the role / team / slug with the user if not obvious.
2. Run research in parallel across the sources above. Use `TaskCreate`
   to track if the work is multi-step.
3. Read enough local skill / runbook files to extract the duty
   catalogue. Cite specific systems and incident families found in
   evidence.
4. Draft the requested artifact(s) to the output paths above.
5. End-of-turn summary: what was written, where, and one suggested
   next step (trim, convert to Google Doc, add placeholder
   quantification, split into recruiter and engineer views, etc.).

## Examples in this repo

- `content/wikis/linkedin/trust-im-ir-engineer-job-description.md` —
  canonical JD example, grounded in the `trustim-investigation`
  plugin's 25+ skill files plus Confluence / JIRA / code sources.
- `content/wikis/linkedin/trust-im-ir-cv-duties.md` — canonical CV
  duties example, external-audience translation of the same research.

Read those before drafting a new one if the structure or tone is
unclear.

## What NOT to do

- Do not generate a JD or CV duties from training data without the
  research phase. The output must be grounded in real evidence from
  the repo / Confluence / JIRA / code.
- Do not invent metrics. If you do not have the number, do not
  quantify.
- Do not name specific colleagues in the artifact (the user does not
  want collaborator names in role-level docs).
- Do not write a tabular role spec. Prose + bullets only.
- Do not pad with generic "responsibilities" that could apply to any
  engineer. Every bullet should be defensible by something you read
  in the research phase.
