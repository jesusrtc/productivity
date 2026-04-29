---
name: publish-audit-trail
description: >-
  Publishes a completed TrustIM investigation audit trail as a formatted Google Doc
  in the TrustIM Investigations shared Drive folder, and updates the master tracking
  document with a summary row. Use at the end of any investigation to close out the
  audit trail required by CLAUDE.md.
allowed-tools: Bash
---

# Publish Audit Trail

## How to Use This Skill

Use this skill **at the end of an investigation** to:
1. Create a formatted findings Google Doc in the TrustIM Investigations Drive folder
2. Append a summary row to the master tracking document

**This skill must NOT write anything to InResponse.** Alert/Incident data is read from InResponse for reference only (via `ir-cli` skill or user-provided values).

---

## Prerequisites — Gather These Before Publishing

Before running the publish steps, confirm you have the following values from the current investigation session:

| Field | Source |
|-------|--------|
| **Alert ID** | InResponse alert (read from `ir alert get {id}` or user-provided) |
| **Incident ID** | InResponse incident linked to the alert (read from `ir incident get {id}` or user-provided; leave blank if none) |
| **Investigation Type** | One of: `ATO`, `Fake Account`, `Scraping`, `ABI Abuse`, `Suspicious Registrations`, `Login Analysis`, `Messaging Abuse`, `SN Abuse`, `Rule Tuning`, `Site Anomaly`, `Domain Investigation`, `Challenge Research`, `Other` |
| **Claude Estimated Sev** | Output of the `sev-assessment` skill — must be `SEV0`–`SEV4` or `No SEV` |
| **Quick Summary** | 1–2 sentence plain-language description of what was found |
| **Audit Trail Content** | All queries, results, and interpretations collected during the investigation per CLAUDE.md rules |

If any of these are missing, ask the user before proceeding.

---

## Step 1: Create the Findings Google Doc

Use the `create_google_docs_document` Captain MCP tool to create a new document.

**Title format:** `Alert {ALERT_ID} — {BRIEF_DESCRIPTION} ({YYYY-MM-DD})`

Example: `Alert 98321 — Bulk Registrations from ghksc.us (2026-03-19)`

**Target folder:** TrustIM Investigations shared Drive
Folder ID: `1Ry3OqQwmq8zE9xeo9QoVoi8fttDPoNbT`
Folder URL: https://drive.google.com/drive/folders/1Ry3OqQwmq8zE9xeo9QoVoi8fttDPoNbT

After creating the doc, note the document URL returned — you will need it for Step 3.

---

## Step 2: Write the Findings Doc Content

Use `write_to_google_docs_document` to populate the doc. Do NOT use markdown — use plain Google Docs formatting (headings via the heading level parameter, tables via table formatting, etc.).

Structure the document as follows:

### Document Structure

**Section 1 — Investigation Overview**
- Date: {YYYY-MM-DD}
- Alert ID: {ALERT_ID}
- Incident ID: {INCIDENT_ID} (or "None")
- Investigation Type: {INVESTIGATION_TYPE}
- Claude Estimated SEV: {SEV_LEVEL}
- Investigator: Claude Code (TrustIM Investigation Plugin)

**Section 2 — Queries and Results**

For each query run during the investigation, include a subsection with:
- Subsection heading: e.g., "Query 1: Registration Volume by Domain"
- The exact SQL query text (verbatim, in a code block or monospace)
- The raw result formatted as a table
- Interpretation: 1–3 sentences explaining what the result shows

Number each query sequentially. Do not omit any query that was used to form a conclusion.

**Section 3 — Findings Summary**

Narrative summary of investigation findings. Every claim must cite a query by number.
Example: "Per Query 3, 345/527 (65%) of registrations originated from GBR."
Do NOT include any finding that does not have a corresponding query in Section 2.

**Section 4 — Assessment**

- Claude Estimated SEV: {SEV_LEVEL} — cite the specific threshold(s) from the `sev-assessment` skill that determined this level, or state "No threshold met" if No SEV.
- WoW T7D computation (if applicable): include the numeric values used.
- Recommended next steps (optional — omit if not applicable).
- Human SEV: [To be filled in by oncall engineer]

---

## Step 3: Update the Master Tracking Document

The tracking log uses a markdown table written via Apps Script — this is the **only** path that creates real clickable hyperlinks in Google Docs table cells. Do NOT use the `elements` approach for this table — it does not support hyperlinks in cells.

**Tracking doc ID:** `1BtRrOb2-G2V7a_P4bPTq-z3_ey9nCYYYVqgsBismPqw`
**Tracking doc URL:** https://docs.google.com/document/d/1BtRrOb2-G2V7a_P4bPTq-z3_ey9nCYYYVqgsBismPqw/edit

### Step 3a — Read the tracking log with links expanded

Use `read_google_docs_document` with:
- `document_id`: `1BtRrOb2-G2V7a_P4bPTq-z3_ey9nCYYYVqgsBismPqw`
- `expand_links`: `true`

From the response, record:
- The `table` element in `element_mapping` → its `start_index` and `end_index`
- The `full_text` field — parse it to recover all existing rows and their `[View Findings](url)` links

To parse the rows: split `full_text` on `\n`, keep lines starting with `|`, skip the separator row (contains only `-` and `|`), split each row by `|`, trim each cell.

### Step 3b — Delete the existing table

Use `write_to_google_docs_document` with:
- `operation`: `delete`
- `start_index`: the table's `start_index` from step 3a
- `end_index`: the table's `end_index` from step 3a

### Step 3c — Append the full updated table as markdown

Use `write_to_google_docs_document` with:
- `operation`: `append`
- `content`: a markdown table string containing the header, all existing rows (with their original `[View Findings](url)` links preserved), and the new row appended at the bottom

**Table columns (in order):**

| Column | Value |
|--------|-------|
| **Date** | Today's date in `YYYY-MM-DD` format |
| **Alert ID** | Alert ID from InResponse |
| **Incident ID** | Incident ID from InResponse, or blank if none |
| **Investigation Type** | One of the types listed in Prerequisites |
| **Claude Estimated Sev** | `SEV0`–`SEV4` or `No SEV` — from `sev-assessment` output |
| **Human Sev** | Always leave blank — filled in manually by the oncall engineer |
| **Model** | The Claude model ID (e.g., `claude-sonnet-4-6`) from the active session |
| **Findings Doc** | Use `[View Findings](url)` syntax with the full URL from Step 1 |
| **Quick Summary** | 1–2 sentence plain-language summary — **last column** |

Example `content` value:
```
| Date | Alert ID | Incident ID | Investigation Type | Claude Estimated Sev | Human Sev | Model | Findings Doc | Quick Summary |
|------|----------|-------------|-------------------|----------------------|-----------|-------|--------------|---------------|
| 2026-03-17 | ALERT-99999 | INC-00001 | ATO | Sev3 |  |  | [View Findings](https://docs.google.com/document/d/...) | Existing row summary. |
| 2026-03-19 | 98321 | None | Suspicious Registrations | SEV3 |  | claude-sonnet-4-6 | [View Findings](https://docs.google.com/document/d/...) | New row being added. |
```

---

## Step 4: Confirm with User

After both writes complete, report back:
- The URL of the findings doc
- Confirmation that the tracking doc was updated
- Ask the user: "The audit trail has been published. Please fill in the Human Sev column in the tracking doc when the incident is closed."

---

## Constraints and Guardrails

- **Never write to InResponse.** Alert and incident data is read-only context.
- **Never publish a findings doc that skips queries.** If Section 2 is incomplete (queries were not run or results are missing), pause and ask the user to confirm before publishing.
- **Never invent or approximate numbers.** All values in Section 3 and 4 must come directly from query results in Section 2.
- **Human Sev must always be left blank.** Claude does not assign the human SEV.
- If the `create_google_docs_document` tool does not support specifying a parent folder directly, create the doc and then inform the user: "The doc was created but could not be placed in the TrustIM folder automatically — please move it to: https://drive.google.com/drive/folders/1Ry3OqQwmq8zE9xeo9QoVoi8fttDPoNbT"
