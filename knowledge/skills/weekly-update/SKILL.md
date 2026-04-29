---
name: weekly-update
description: >-
  Generate the IM Weekly Update report for the skip-level director (Will Nulland).
  Use every Friday EOD or when the user asks to prepare the weekly update.
  Gathers org-scope context from cerebro, accepts external input, and produces
  a plain-text 3-section report. Saves the approved report to im_weekly_update/.
---

# IM Weekly Update

Generate the weekly status report for the IM Weekly Update (submitted to Will Nulland via Google Form).

## Audience

Skip-level director. Write for impact and outcomes, not implementation details. Mention what was done and why it matters. Keep language accessible — no unexplained jargon.

## Output Format

Plain text bullet points only. NO markdown formatting (no bold, no headers, no backticks, no asterisks). Links are encouraged.

The report has exactly three sections with these exact headers:

This Week's P0s:
<usually empty — see P0 rules below>

This Weeks Work:
- <what was done> <why it matters> <link if available>

Next Weeks Work:
- <upcoming item>

### P0 Rules

P0s are rare (~30% of weeks). Do NOT suggest P0s by default. Only flag a P0 candidate if something truly stands out: shipped a major feature, resolved a SEV, or removed a critical blocker. If you identify a P0 candidate, present it separately and ask: "Do you want to include this as a P0?" If the user says no, or nothing qualifies, leave the section empty.

### Writing Style

- 1-2 sentences per bullet max
- Lead with what was done, follow with why it matters
- Include links (PRs, Google Docs, incidents) when available
- No jargon without context
- Tone: professional, direct, confident
- Plain text only — no markdown

## Workflow

Follow these steps in order:

### Step 1: Determine the week

Calculate the current ISO week. The report covers Monday through Friday of the current week. Compute:
- The Monday date (start of week)
- The Friday date (end of week)
- The ISO week number (e.g., W14)

### Step 2: Auto-gather from cerebro

Read ALL of the following org-scope sources. Do not skip any.

NOTE: This source list is expected to evolve as cerebro matures. If sources are added or removed in the future, update this list.

1. Current week's LinkedIn log: `logs/linkedin/YYYY-Www.md` (e.g., `logs/linkedin/2026-W14.md`)
   - This is the primary source. Read the full file.

2. DASHBOARD.md at the repo root
   - Look at: "Current Focus", "This Week", "Blocked / Waiting", "Upcoming", "Project Status"

3. Meeting notes from this week: any files matching `meetings/YYYY-MM-DD-*.md` where the date falls within Mon-Fri of the current week AND `scope: org` in frontmatter
   - Read each matching file.

4. Roadmap files: read all files in `roadmaps/` — use these for "Next Week" context.
   - Skip `roadmaps/productivity-cerebro.md` and `roadmaps/productivity-apps.md` (personal scope).

5. Run `./find.sh open` to find unchecked todo items — include only org-scoped items.

After gathering, present a brief summary of what you found:
"Here's what I found in cerebro for week W{nn} ({monday} - {friday}):
- Log: {number of entries/days with content}
- Dashboard: {key focus items}
- Meetings: {count} meeting notes
- Open todos: {count} org-scoped items"

### Step 3: Ask for external context

Say exactly:
"Paste any additional context for this week's report — notes, links, PRs, Slack threads, Google Docs. Or say 'none' if cerebro has everything."

Wait for user input before proceeding.

### Step 4: Synthesize the report

Combine all gathered context into the 3-section format.

For "This Weeks Work":
- Group related items (don't list 5 bullets about the same project if one covers it)
- Each bullet: what was done + why it matters + link if available
- Only include org-scope work. Exclude personal projects (cerebro, apps, personal productivity tools).

For "Next Weeks Work":
- Pull from DASHBOARD.md "Upcoming" and "This Week" unchecked items
- Pull from roadmap next phases
- Include anything the user mentioned in external context about upcoming work

For "This Week's P0s":
- Review all items. If any truly stand out (SEV resolved, major feature shipped, critical blocker removed), flag them as P0 candidates.
- If no P0 candidates: leave empty, do not ask.
- If P0 candidates exist: present them and ask "Do you want to include this as a P0?" before adding.

### Step 5: Present the draft

Show the full report as plain text in the terminal. Prefix it with:
"--- DRAFT: IM Weekly Update W{nn} ---"

And suffix with:
"--- END DRAFT ---
Approve this draft? (yes / edits needed)"

### Step 6: Handle approval

If user approves:
- Propose a highlight slug based on the most prominent work item (e.g., "scraping-alert-e2e")
- Ask: "Filename: im_weekly_update/{monday-date}-{slug}.md — ok or different slug?"
- On filename approval, save the file (see Saved File Format below)
- Print: "Report saved to im_weekly_update/{filename}"
- Print: "Submit here: https://docs.google.com/forms/d/e/1FAIpQLSdJ0WMIosFlQXREvYFbZFd-nXNkP2n-i1f1LBqpTRSA2jsCtw/viewform"

If user requests edits:
- Apply the edits
- Re-present the draft
- Repeat until approved

## Saved File Format

The archived file uses cerebro YAML frontmatter for searchability via find.sh. The body is the exact plain text for the Google Form.

```
---
title: "IM Weekly Update - W{nn}"
date: {monday-date}
type: weekly-update
scope: org
projects: [{list of projects mentioned in the report}]
tags: [weekly-update]
---

Report for: jcortes@linkedin.com
Week: {YYYY}-W{nn} (Mon {month day} - Fri {month day})

This Week's P0s:
{content or empty}

This Weeks Work:
{content}

Next Weeks Work:
{content}
```

## What This Skill Does NOT Do

- Weekly planning or objective setting
- Auto-submit to the Google Form
- Pull from external systems (GitHub, JIRA, Slack) — relies on cerebro + user paste
- Include personal-scope work (cerebro, apps, personal tools)
