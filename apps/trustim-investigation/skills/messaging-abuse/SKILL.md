---
name: messaging-abuse
description: >-
  Investigate messaging and invitation abuse using Trino queries. Covers spam invitation
  detection, mass messaging, group spam, and invitation delay rule analysis.
  Use when oncall for messaging/invitation abuse spikes.
allowed-tools: Bash
---

# Messaging & Invitation Abuse Investigation

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
| `tracking.scoreevent` | Score events for invitation scoring |
| `tracking_column.scoreEvent` | Columnar score events |
| `u_metrics.dim_member_messaging_daily` | Daily messaging metrics |
| `u_metrics.member_handles_union` | Member handle data |

## Investigation Queries

The SQL for all queries below lives in the **`invitation-scoring`** action skill. Invoke that skill and use the named query listed for each step.

### 1. Mass Invitation Sender Detection
**Action:** `invitation-scoring` → *Mass Invitation Sender Detection via Score Events*
- Params: `{DATE}` — the target date
- Use to find members sending unusually high invitation volumes (50+ in a day)

### 2. Invitation Delay Rule Impact
**Action:** `invitation-scoring` → *Invitation Delay Rule Impact*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to track how many members are caught by DELAY rules over time

### 3. Invitation Counter Analysis
**Action:** `invitation-scoring` → *Invitation Counter Analysis*
- Params: `{DATE}` — the target date
- Use to see distribution of 24-hour invitation counter values per member

### 4. Messaging Abuse by Type
**Action:** `invitation-scoring` → *Messaging Abuse by Type*
- Params: `{DATE}` — the target date
- Use to analyze non-connection messaging volume by message type and entry point

### 5. Group Spam Detection
**Action:** `invitation-scoring` → *Group Spam Detection*
- Params: `{START_DATE}` — start of the date range
- Use to find members making 10+ posts in LinkedIn groups

### 6. Invitation Damage Assessment
**Action:** `invitation-scoring` → *Invitation Damage Assessment*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` and `{SPAMMER_TABLE}` to the headless schema/table holding suspected spammers
- Use to measure total victim count and damage from confirmed spammers

## Groups Messaging Abuse (FrostGuard)

FA and ATO accounts exploit LinkedIn Groups to send 1:1 messages to non-connected members at scale, bypassing normal messaging restrictions.

### Scale
- ~50% of all Groups messages are from abusive accounts (as of Jan 2024)
- ~37.6K abusers sent 15M messages across 59.8K groups
- ~600K/week FA UMI increase attributable to groups messaging

### Detection Signals
- Average 9.03 seconds between messages (automation signal) — 4x faster than normal users
- Precision at msg_count >= 200/day: ~89%
- Tables: `u_metrics.abuse_damage_fake_account_union` JOIN `u_metrics.message_request_sent_union`
- Event: `message_request_compose_sent` for `LINKEDIN_GROUP` type

### Reference
- [Groups messaging abuse investigation](https://docs.google.com/document/d/1_XBp5yYvLNeOGyndB_6I-7P2kbEkZ0y1O5Y_eB1_wrM/edit)

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `KeywordsAnalysisWidget` | `KeywordsAnalysisWidget(keywords=["crypto investment", "work from home"], period="7d")` | Find members searching spam-related keywords across federated search events |
| `SearchTermRankingWidget` | `SearchTermRankingWidget(mids=[MID1, MID2], period="30d")` | Rank search terms for suspected spammer MIDs — reveals targeting patterns |

## Tips

- Invitation scoring: `scorertype = 'SCORER_MEMBER_REQUEST'`
- Content classification: `scorertype = 'SCORER_CONTENT_CLASSIFICATION'`
- `DELAY` decision means invitation was delayed (friction applied)
- Track non-connection messages as a spam signal
- Cross-reference with fake account union for known abusers
