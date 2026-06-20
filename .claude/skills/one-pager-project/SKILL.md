---
name: one-pager-project
description: >-
  Draft a project one-pager (RFC / proposal / vision doc / concise pitch)
  for alignment with leadership or cross-functional stakeholders.
  Plain-text, ≤5000 chars, no markdown formatting, no technical
  deep-dives. Use when the user wants a project / initiative / proposal
  doc for human alignment — NOT for code review, rule iteration, or
  investigation summaries. Triggers: "project one-pager", "vision doc",
  "RFC for {X}", "short pitch for {Y}", "alignment doc", "proposal for
  {Z}".
---

# Project one-pager

Output goes to `projects/<id>/docs/one-pager.md`. **Never
publish to Google Docs.** Local file only.

## When to use this vs. the technical one-pager skills

- Audience is leadership / cross-fn / partner teams, goal is agreement
  on direction → **this skill**.
- Audience is code reviewers / TRex iteration owners, goal is rule
  design → `one-pager-asta`.
- Audience is incident responders / engineers / leadership reading an
  incident summary → `one-pager-investigation`.

RFCs currently go through this skill. If RFCs need a separate format
later, a dedicated `one-pager-rfc` skill can be split out.

## Ask first (single message, then wait)

Before writing, ask the user these in one message and wait for answers:

1. What is the project or initiative about? (Brain dump — I'll structure it.)
2. Who is the audience? (Eng team / cross-fn / leadership / partner teams.)
3. What is the problem or motivation? Why does this matter now?
4. Do you have a proposed solution or approach in mind?
5. Specific requirements or constraints to capture?
6. Stakeholders section? If so, who and their roles?
7. Open questions or decisions still pending?

## Output skeleton (plain text, no markdown)

```text
[Project Name] — One Pager

Background
[1–2 paragraphs. Why this matters. Current state. Why action is needed.
Lead with the "why".]

Proposed Solution
[1–2 paragraphs. High-level approach. Non-technical-friendly. What and
why this approach, at a level any stakeholder can follow.]

Requirements
- Clear, actionable statement of what must be true for the project to succeed.
- Another requirement.
- Edge case or boundary condition.

Stakeholders (optional)
- Role: Name — area of responsibility
- Role: Name — area of responsibility

Glossary (optional)
- Term A: Brief definition of the concept or acronym.
- Term B: Brief definition of the concept or acronym.

Open Questions (optional)
- Question about scope or approach, with any preliminary direction.
- Decision: Resolution if already decided.
```

## Rules

- **≤5000 chars total. 1–2 pages.** If it spills past that, cut.
- **Lead with "why."** Reader should understand within the first
  paragraph why this matters and what changes if it happens.
- **Short paragraphs (2–3 sentences max).** Bullets for requirements and
  lists.
- **No code, schemas, regexes, or technical deep-dives.** If the reader
  needs implementation detail, this is the wrong skill — use
  `one-pager-asta` (for rules) or write a technical design doc
  separately.
- **Plain text. No markdown headers / bold / tables.** Use simple
  structure: header lines without `#`, bullets as `- `. The output
  should read as well in a Slack paste as in a doc.
- Cut anything that doesn't help the reader understand the problem or
  the solution.
- No Google Docs publishing. Ever.
