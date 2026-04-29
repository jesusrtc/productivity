---
name: headless-investigation
description: >-
  Autonomous investigation mode that uses InResponse as the entry point. Given an alert ID
  or incident ID, fetches all context from InResponse (ir CLI), determines the investigation
  type, selects the appropriate investigation skill, runs the investigation without user input,
  performs a SEV assessment, and publishes the audit trail. Use when the user provides an alert
  or incident ID and wants a fully autonomous investigation.
allowed-tools: Bash
---

# Headless Investigation

## When to Use This Skill

Use this skill **only when the user explicitly requests headless mode** (e.g., "run headless on alert 249973199", "headless investigate incident 260376352"). Simply providing an alert or incident ID without the word "headless" should default to interactive mode. This skill replaces the normal "ask first" investigation flow with a "gather from InResponse first" approach.

**This skill overrides the "Never Assume — Ask" rule from CLAUDE.md** for the specific questions that InResponse data can answer. You still ask the user when InResponse data is insufficient.

**CRITICAL: InResponse is READ-ONLY in headless mode.** Never use `ir` CLI write commands (`ir alert edit`, `ir alert dismiss`, `ir alert promote`, `ir alert attach`, `ir alert detach`, `ir incident edit`, `ir incident comment add`, `ir incident timeline add`, `ir incident link`). Only use read commands: `ir alert view`, `ir incident view`, `ir incident timeline list`, `ir alert list`, `ir incident list`. If the investigation produces findings that should update the incident (e.g., SEV change, status update, comments), document them in the audit trail Google Doc and inform the user — never write them to InResponse directly.

---

## Phase 1: InResponse Context Gathering

### Step 1a: Determine Entry Point

- If the user provides an **alert ID** → start with the alert, then follow to its incident
- If the user provides an **incident ID** → start with the incident, then enumerate its alerts

### Step 1b: Fetch Alert Details

```bash
ir alert view {ALERT_ID} --json
```

Extract and record:
| Field | Used For |
|-------|----------|
| **Title** | Keyword routing to investigation skill |
| **Type** | Primary routing signal (maps to InResponse enum) |
| **Source** | Context (ATT&CK, Iris, manual, etc.) |
| **Entity Impact** | Scope (Members, Guest, Jobs, etc.) |
| **Service Impact** | Affected service |
| **Severity** | Current severity label |
| **Incident** | Linked incident ID (follow to Step 1c) |
| **Incident Date** | Start of the investigation date range |
| **Created** | Alert creation time — use for date range |
| **Description** | May contain IOC details, metric names, thresholds |
| **Note** | May contain oncall notes or prior analysis |
| **Detected by Trust Monitoring** | Whether automated detection fired |

### Step 1c: Fetch Incident Details (if linked)

```bash
ir incident view {INCIDENT_ID}
ir incident timeline list {INCIDENT_ID}
```

Extract and record:
| Field | Used For |
|-------|----------|
| **All alerts** | Full scope — how many alerts, date span, are they the same type? |
| **Post-Triage Sev** | Current SEV assignment to compare against |
| **Status** | Investigation state (Open, Triaged, Active, etc.) |
| **Timeline** | Key events, SEV changes, prior actions taken |
| **Comments** | Prior investigation notes or context |
| **Started At / First Response** | For TTD/TTR calculation |
| **Teams** | Which team owns this |

### Step 1d: Fetch Sibling Alerts

For up to 10 alerts listed in the incident, run `ir alert view {SIBLING_ID} --json` to check:
- Are the alerts the same type or different facets of the same attack?
- What is the full date span across all alerts?
- Do descriptions or notes contain different IOCs or details?

### Step 1e: Derive Investigation Parameters

From the gathered data, determine:

| Parameter | How to Derive |
|-----------|---------------|
| **Date range** | Earliest alert `Incident Date` through today (or `Finished At` if incident is closed) |
| **Investigation type** | See Phase 2 routing table |
| **IOC hints** | From alert Title, Description, Note fields — look for domain names, IP ranges, member IDs, metric names |
| **Urgency** | From Severity field and whether alerts are still firing (multiple recent alerts = active attack) |
| **Prior findings** | From incident Comments and Timeline |

---

## Phase 2: Investigation Skill Routing

### Primary Routing: InResponse Type Enum

The alert `Type` field maps directly to investigation skills:

| InResponse Type | Investigation Skill | Headless Account |
|----------------|--------------------|--------------------|
| `ATO` | `account-takeover` | `ir2ato` |
| `Fake Accounts` | `fake-account-research` | `ir2fake` |
| `Guest Scraping` | `scraping-investigation` | `ir2scraping` |
| `Member Scraping` | `scraping-investigation` | `ir2scraping` |
| `Private Messaging` | `messaging-abuse` | `trustim` |
| `Scams-Malware/Phishing` | `account-takeover` | `ir2ato` |
| `Scams-Money` | `fake-account-research` | `ir2fake` |
| `DOS/DDOS` | `site-anomaly` | `trustim` |
| `Jobs & Payments` | `oncall-triage` | `jobstrust` |
| `Jobs Fraud` | `oncall-triage` | `jobstrust` |
| `Enterprise Violations` | `sn-abuse` | `ir2fake` |
| `Public Content-Hate Speech` | `oncall-triage` | `trustim` |
| `Public Content-Misinformation` | `oncall-triage` | `trustim` |
| `Premium Ads Fraud` | `oncall-triage` | `trustim` |
| `Other` | **Use secondary routing (below)** | — |

### Secondary Routing: Title Keyword Matching

When `Type` is `Other` or the primary mapping is ambiguous, match keywords in the alert **Title** and **Description**:

| Keywords (case-insensitive) | Investigation Skill |
|---------------------------|---------------------|
| `registration`, `signup`, `reg spike`, `IOC spike`, `automation at reg`, `QCS throttle`, `reg QPS`, `registration QPS` | `suspicious-registrations` |
| `login`, `auth failure`, `credential`, `password reset`, `list washing` | `login-analysis` |
| `invitation`, `ABI`, `invite spam`, `contacts upload`, `bulk invite` | `abi-abuse` |
| `challenge`, `captcha`, `phone challenge`, `email PIN`, `IRSF`, `VoIP` | `challenge-research` |
| `rule`, `FPR`, `false positive`, `drools`, `model performance` | `rule-tuning` |
| `QPS`, `traffic spike`, `site speed`, `IPv6`, `bot wave` | `site-anomaly` |
| `Sales Navigator`, `SN abuse`, `recruiter`, `free trial`, `contract` | `sn-abuse` |
| `scraping`, `data egress`, `denial event`, `block filter` | `scraping-investigation` |
| `messaging`, `group spam`, `InMail`, `non-connection message` | `messaging-abuse` |
| `fake romance`, `romance scam`, `bcookie fanout`, `name change` | `fake-account-research` |
| `domain`, `email domain`, `MX record`, `disposable domain` | `domain-investigation` |
| `DIHE`, `UMI`, `member report`, `self report` | Start with `sev-assessment` directly |

### Tertiary Routing: Entity Impact

If both Type and Title are ambiguous, use Entity Impact:

| Entity Impact | Default Skill |
|---------------|---------------|
| `Members` | `oncall-triage` → pivot based on first query results |
| `Guest` | `scraping-investigation` or `site-anomaly` |
| `Jobs` / `LTS (Hiring)` | `oncall-triage` with `jobstrust` |
| `LSS (Sales)` | `sn-abuse` |

### Routing Attempt Limit

You have a **maximum of 15 routing attempts** across all phases (primary, secondary, tertiary routing decisions and cross-skill pivots during Phase 3). Each routing decision or pivot counts as one attempt.

If you reach 15 attempts without confidently selecting a single investigation skill, proceed to **Routing Failure**.

### Routing Failure

If no routing matches after exhausting all routing levels, or the routing attempt limit (3) is reached, state: "I could not determine the investigation type from InResponse data. The alert Type is '{Type}' and Title is '{Title}'." Then publish an update to the tracker sheet that this alert requires manual review for routing and end the investigation.

---

## Phase 3: Execute Investigation

Once the skill is selected:

1. **Announce the plan**: "Based on InResponse data, this is a {type} investigation. I'll use the `{skill}` skill with date range {start}–{end}. Starting with {first query description}."

2. **Follow the selected skill's query sequence** using the parameters derived in Phase 1e. Run queries from the skill's action references in order.

3. **Use the date range from InResponse**:
   - **Start date**: Earliest alert `Incident Date` minus 7 days (for baseline/WoW comparison)
   - **End date**: Today's date (to check if the attack is ongoing)
   - **Alert window**: Earliest `Incident Date` through latest alert `Created` date
   - **Maximum date range: 90 days.** If the computed range or look back exceeds 90 days, cap the start date at 90 days before the end date. This prevents expensive full-table scans. If the alert's Incident Date is older than 90 days, note the truncation in the audit trail.

4. **If the skill has numbered investigation steps**, follow them in order. At natural breakpoints (every 3–4 queries), summarize findings so far in the conversation.

5. **Cross-skill pivots**: If initial queries reveal a different attack type than expected (e.g., registration alert reveals ATO pattern), state the pivot: "Initial queries suggest this is actually {new_type}. Pivoting to `{new_skill}`."

---

## Phase 4: SEV Assessment

After the investigation queries are complete, run the `sev-assessment` skill:

1. **Identify which metrics to check** based on the investigation type:
   - Registration/FA attacks → FA member reports (FAKE_IDENTITY) T7D WoW + cohort DIHE
   - ATO attacks → ATO self reports (TS-RHA) T7D WoW + ATO member reports (ACCOUNT_HACKED) T7D WoW
   - Scraping → Projected scraped data
   - Messaging/ABI → Projected DIHE (invites and messages)
   - Content → Public/Private Content Reports T7D WoW

2. **Run the T7D WoW computation** using the SQL templates from `sev-assessment`

3. **Apply thresholds** from Table 1 (True North) or Table 2 (Cohort-based)

4. **Check modifiers** — boost/demote factors

5. **Compare to current InResponse SEV** — note if the computed SEV differs from what's already assigned

---

## Phase 5: Publish Audit Trail (Default)

In headless mode, **always publish the audit trail** unless the user explicitly says not to. Follow the `publish-audit-trail` skill for full instructions, and apply the `investigation-report-standards` skill for all output formatting (language rules, notebook structure, recommendation formatting). The critical steps are:

1. **Create the findings Google Doc in the TrustIM shared folder** — use `parent_folder_id: 1Ry3OqQwmq8zE9xeo9QoVoi8fttDPoNbT` when calling `create_google_docs_document`. If you already created a doc earlier in the investigation without this folder ID, create a new doc in the correct folder and copy the content over.
2. **Write all queries, results, and interpretations** as structured sections following the document structure in `publish-audit-trail` (Investigation Overview → Queries and Results → Findings Summary → Assessment).
3. **Update the master tracking document** (doc ID: `1BtRrOb2-G2V7a_P4bPTq-z3_ey9nCYYYVqgsBismPqw`) — you **MUST** follow the 3-step process from `publish-audit-trail` Steps 3a–3c exactly:
   - **3a:** Read the doc with `expand_links: true`, record the table's `start_index` and `end_index`, and parse existing rows from `full_text` (preserving `[View Findings](url)` links).
   - **3b:** Delete the existing table using `operation: delete` with the recorded start/end indices.
   - **3c:** Append the full updated table using `operation: append` with `content` (a markdown string). **Do NOT use `elements`/`table_info`** — only the markdown `content` path goes through Apps Script, which is the only way to create clickable hyperlinks in table cells.
4. **Report back** — provide the findings doc URL, confirm the tracking doc was updated, and instruct the user to fill in the Human Sev column when the incident is closed.

---

## Summary: What InResponse Answers vs What Still Requires User Input

### InResponse answers these (do NOT ask the user):
- Date range (from alert/incident timestamps)
- Investigation type (from Type + Title routing)
- Which metric spiked (from Title + Description)
- Urgency (from Severity + alert frequency)
- Prior investigation context (from Comments + Timeline)
- Whether to create audit trail (default: yes in headless mode)

### Still ask the user when:
- InResponse data is empty/ambiguous AND routing fails
- Query results are ambiguous with multiple valid interpretations
- A cross-skill pivot is needed (confirm before switching)
- The computed SEV differs significantly from the current assignment
- Evidence conflicts with the initial hypothesis
- The investigation requires access to a table/schema you haven't used before
