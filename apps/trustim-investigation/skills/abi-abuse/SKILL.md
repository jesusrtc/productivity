---
name: abi-abuse
description: >-
  Investigate Addressbook Import (ABI) and bulk invitation abuse using Trino queries.
  Covers ABI flow analysis, contacts upload detection, bulk invitation patterns,
  and invitation click tracking. Use for invitation spam and ABI-based attacks.
allowed-tools: Bash
---

# ABI & Bulk Invitation Abuse Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'trustim';`

Other headless accounts: `ir2fake`, `ir2ato`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking_column.InvitationClickEvent` | Invitation click tracking |
| `tracking.contactsuploadevent` | Contacts upload / addressbook import events |
| `tracking.InvitationScoreEvent` | Invitation scoring decisions |
| `tracking.scoreevent` | General score events (SCORER_MEMBER_REQUEST) |
| `data_derived.InvitationHistory` | Historical invitation data |

## Investigation Queries

The SQL for all queries below lives in the **`invitation-scoring`** action skill. Invoke that skill and use the named query listed for each step.

### 1. ABI Flow Analysis
**Action:** `invitation-scoring` → *ABI Flow Analysis*
- Params: `{DATE}` — the target date
- Use to see which ABI flows, products, and subproducts have high volume

### 2. Contacts Upload Volume
**Action:** `invitation-scoring` → *Contacts Upload Volume*
- Params: `{START_DATE}` — start of the date range
- Use to detect members uploading 500+ contacts; adjust the `HAVING` threshold as needed

### 3. Bulk Invitation Senders via Score Events
**Action:** `invitation-scoring` → *Mass Invitation Sender Detection via Score Events*
- Params: `{DATE}` — the target date
- Use to find members sending 50+ invitations through the scorer in a single day

### 4. Invitation Damage from ABI Abusers
**Action:** `invitation-scoring` → *Invitation Damage from ABI Abusers*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` to the headless schema holding the ABI abuser table
- Use to measure victim count and total damage from confirmed ABI abusers

### 5. Connection Break Analysis Post-Invitation
**Action:** `invitation-scoring` → *Connection Break Analysis Post-Invitation*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` to the headless schema holding the ABI abuser table
- Use to measure downstream victim awareness (connection breaks indicate recipients recognized the spam)

### 6. Invitation Skew Features
**Action:** `invitation-scoring` → *Invitation Skew Features*
- Params: `{MEMBER_IDS}` — comma-separated list of suspected ABI abuser member IDs
- Use to check targeting skew (gender, industry concentration) for the suspected abusers

## Tips

- ABI flow: `tracking.contactsuploadevent` for upload events, `InvitationClickEvent` for click tracking
- Invitation scoring: `scorertype = 'SCORER_MEMBER_REQUEST'` in score events
- `DELAY` decision = invitation delayed (friction), `ACCEPT` = passed through
- Key paths: `%voyagerGrowthNormInvitations%` for standard invitations, `%action=batchCreate%` for batch
- Damage measurement: `u_metrics.harm_union` with `damage_type = 'RECEIVED_INVITATION'`
- Invitation skew features in `u_secaggs.invitation_skew_features` can detect targeting patterns
- Connection breaks post-invitation indicate victim awareness of spam
