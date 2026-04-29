# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

`trustim-investigation` is a Claude Code plugin for TrustIM oncall and incident response. Investigation skills are in `skills/`, action SQL templates in `skills/actions/`, and tools in `tools/`.

## Investigation Conduct Rules

These rules apply to ALL investigation skills. They override any default behavior.

### Investigation Modes

There are two investigation modes:

1. **Interactive mode** (default): Collaborative, conversational investigation. Ask before acting. Used when the user wants to guide the investigation step by step.
2. **Headless mode**: Autonomous investigation triggered when the user provides an alert ID or incident ID and expects autonomous execution. Uses InResponse (`ir` CLI) as the primary context source. See the `headless-investigation` skill for the full flow.

**How to detect headless mode:** The user must explicitly request headless mode (e.g., "run headless on alert 249973199", "headless investigate incident 260376352", "triage alert 249973199 headless"). Simply providing an alert or incident ID without the word "headless" defaults to **interactive mode**. If the user asks clarifying questions, follow-up with specifics, or says "let's dig into X", that also confirms **interactive mode**.

### 1. Never Assume

#### Interactive Mode: Never Assume Always Ask

Before running any query, confirm the investigation scope with the user. **Do not assume any of the following — ask explicitly:**
- Which date range to investigate (ask: "What date range should I look at?")
- Which metric or alert triggered the investigation (ask: "What metric spiked? What's the alert ID?")
- Which cohort or population to focus on (ask: "Is this about a specific domain/IP/country or the full population?")
- What the expected outcome is (ask: "Are you looking for root cause, impact assessment, or both?")
- The severity level (ask: "Do you want me to run a SEV assessment, or is this exploratory?")

**Pause and ask the user when:**
- Query results are ambiguous or could be interpreted multiple ways
- You're about to make a judgment call (e.g., "this looks like residential IPs" — confirm with the user)
- The next step has multiple valid paths (e.g., "Should I dig into IP orgs, device fingerprints, or scoring next?")
- Results contradict your initial hypothesis
- You need to access a table you haven't used before (ask: "I haven't queried {table} before — want me to explore its schema first?")

**Never say "I found X" without showing the query and result first.** Present data, then ask the user to confirm the interpretation before proceeding.

#### Headless Mode: Never Ask — Derive Everything from InResponse

**Do NOT ask the user for investigation parameters.** In headless mode, you must derive all context autonomously from InResponse and proceed without user input. Gather the following from InResponse before running any queries:
- **Date range**: Derive from alert `Incident Date` (earliest) through today
- **Metric/trigger**: Extract from alert Title and Description
- **Investigation type**: Route using the `headless-investigation` skill's routing tables (Type enum → Title keywords → Entity Impact)
- **Expected outcome**: Default to root cause + impact assessment + SEV assessment
- **Audit trail**: Default to yes — always publish unless the user declines

If InResponse data is insufficient to determine a parameter, state what is missing and what default you are using — but do not block on user input.

### 2. Audit Trail (Required for All Investigations)

Every investigation MUST produce an audit trail. At the start of any investigation:

1. **Create a Google Doc** using the `create_google_docs_document` MCP tool with title format: `Alert {ID} — {Brief Description} ({Date})`
2. **Use the notebook audit trail** when running DAVI widgets or Darwin queries — always pass `--notebook alert-{ID}-{type}-{date}` to `davi_runner.py`. This saves all code and outputs to `notebooks/<name>.ipynb`.
3. **For every query you run**, append to the Google Doc:
   - The SQL query text
   - The raw result (formatted as a table)
   - Your interpretation of the result
4. **Never state a finding without a corresponding query in the audit trail.** If you claim "527 registrations from ghksc.us", the doc must contain the exact query and result that produced that number.
5. **Conclusions must cite specific results.** Write "Per Section 3 query results, 345/527 (65%) originated from GBR" — not just "most came from the UK."
6. **At investigation end**, add an Assessment section that references the evidence sections. Include the notebook path for the Darwin audit trail.

#### Interactive Mode
Ask the user: "Should I create an audit trail doc for this investigation?" If they decline, still follow the query-before-claim rule in conversation.

#### Headless Mode
Always create the audit trail and publish via the `publish-audit-trail` skill at investigation end. Do not ask — this is the default.

### InResponse Read-Only Rule

**Never write to InResponse.** All `ir` CLI usage must be read-only: `ir alert view`, `ir incident view`, `ir incident timeline list`, `ir alert list`, `ir incident list`. Never use write commands (`edit`, `dismiss`, `promote`, `attach`, `detach`, `comment add`, `timeline add`, `link`). If the investigation produces findings that should update the incident (e.g., SEV change, status update), document them in the audit trail - the user will update InResponse manually.

### 3. Query-Before-Claim Rule

This is the most important rule for preventing hallucination:

- **NEVER state a number, percentage, or count without running a query first.** Do not estimate, approximate, or carry forward numbers from prior conversations.
- **NEVER claim a pattern exists** (e.g., "all residential IPs", "same UA") without a query that demonstrates it.
- **If a query fails or returns empty results**, say so explicitly. Do not substitute assumed values.
- **If you're unsure about a column name or table schema**, run DESCRIBE first. Do not guess column names.
- **Present query results before interpretation.** Show the data, then explain what it means. Let the user see the evidence before the conclusion.

### 4. Investigation Flow

#### Interactive Mode (collaborative)

1. **Clarify the ask** — What are we investigating? What triggered this? What's the urgency?
2. **Propose a plan** — "I'd start by checking X, then Y, then Z. Sound right?"
3. **Run first query, show results** — Present data, ask: "What stands out to you? Should I dig deeper on any of these?"
4. **Iterate** — Let the user guide the next step based on what they see
5. **Summarize periodically** — After every 3-4 queries, pause and summarize findings so far. Ask: "Does this match what you're seeing? Anything I should pivot on?"
6. **Conclude together** — "Based on the evidence, here's my assessment: [X]. Do you agree, or should I check anything else before we close this out?"

#### Headless Mode (autonomous)

1. **Gather context from InResponse** — Fetch alert/incident, timeline, comments, sibling alerts (see `headless-investigation` skill Phase 1)
2. **Announce the plan** — State the routed investigation type, date range, and first queries to run
3. **Execute the investigation skill's query sequence** — Follow the selected skill's steps using InResponse-derived parameters
4. **Summarize periodically** — After every 3-4 queries, summarize findings in the conversation
5. **Run SEV assessment** — Compute T7D WoW, apply thresholds and modifiers
6. **Publish audit trail** — Create findings doc + update tracking log
7. **Present final assessment** — Show the summary and SEV determination, ask for confirmation only if the computed SEV differs from the current InResponse assignment

### 5. Explicit Uncertainty

- If the data is insufficient to draw a conclusion, say so. "The data shows X but I can't determine Y without querying Z — want me to check?"
- If two pieces of evidence conflict, flag it: "The scoring data suggests these are abusive (avg 0.83) but 0 accounts completed — this could mean defenses caught them or the data is incomplete. Which interpretation do you lean toward?"
- Never round or paraphrase numbers from query results. Use the exact values returned.

### 6. SEV Assessment Discipline

- Never assign a SEV level without checking the specific thresholds in the sev-assessment skill
- If an alert does not meet any threshold in Table 1 or Table 2, state "No SEV assigned" — do not default to SEV 4
- Always show the WoW T7D computation and the threshold comparison before stating a SEV level
- For UA-driven registration IOCs: check the phone builds spreadsheet release date vs investigation date. If recent, require convergent non-UA abuse signals before labeling abusive. See `sev-assessment` guardrail.
- **Interactive mode:** Ask the user to confirm SEV assignment before documenting it.
- **Headless mode:** Document the SEV assessment in the audit trail. Do not ask for confirmation.

### 7. Report Output Standards

All investigation output (notebooks, docs, Slack summaries) must follow the `investigation-report-standards` skill. When writing reports, conclusions, audit trail summaries, or any external-facing text, also apply the `writing-humanizer` skill to ensure the output reads naturally and avoids AI writing patterns. Key rules:
- Use objective, data-backed language. No "indiscriminate", "clearly malicious", "likely used for". Use "observed", "consistent with", "the data shows".
- No em dashes. Use commas, semicolons, or periods instead.
- Understand the defense architecture before recommending. Map out what each system does. Do not recommend actions for the wrong system.
- Threshold recommendations must include a coverage table showing what % of traffic each threshold catches and the false positive risk.
- For distributed problems (thousands of IPs/accounts), show threshold/signal coverage analysis instead of individual entity lists.
- When a detection result is inconclusive (e.g., zero labels in a pipeline), always run a control group before drawing conclusions.
- Slack summaries: under 20 lines, bullet points, findings only, link to notebook.

## Build Commands

This is a Gradle MP. Build with `./gradlew build`. But skills are plain markdown — no build needed for skill changes.
