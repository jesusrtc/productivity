---
name: one-pager
description: >-
  Draft a one-pager (RFC / proposal / vision doc / concise pitch) for a project.
  Use when the user asks for a one-pager, RFC, proposal, vision doc, or short
  pitch. Produces a single-page markdown doc following the standard structure:
  TL;DR, Context, Proposal, Approach, Risks, Open questions, Review table.
---

# One-pager skill

Use when: a user wants to draft an RFC, proposal, vision doc, or concise pitch.

## Structure

```
# <Title>

**Status:** Draft | In review | Approved
**Date:** YYYY-MM-DD
**Owner:** Name

## TL;DR
<2-3 sentences — what + why + outcome>

## Context
<Why this matters now. What's the problem or opportunity?>

## Proposal
<What we're going to do. Narrow enough to execute, broad enough to matter.>

## Approach
<How — the 3-5 key moves, not implementation detail>

## Risks + mitigations
<What could go wrong and the plan>

## Open questions
<Things we don't know yet, for reviewers>

## Review table
| Reviewer | Role | Feedback | Resolved |
|---|---|---|---|
```

## Rules

- One page. If it spills over two screens, cut.
- Lead with the outcome, not the history.
- Name owners and reviewers explicitly. Avoid passive voice.
- If you can't state the TL;DR in 3 sentences, the proposal isn't ready.
