---
name: sn-abuse
description: >-
  Investigate Sales Navigator abuse using Trino queries. Covers SN free trial abuse,
  contract-level fake account clustering, name change detection, and recruiter seat analysis.
  Use when investigating SN/recruiter related abuse patterns.
allowed-tools: Bash
---

# Sales Navigator Abuse Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'ir2fake';`

Other headless accounts: `trustim`, `jobstrust`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `prod_foundation_tables.dim_sales_navigator_seats` | SN seat assignments with contract/role data |
| `u_metrics.lss_dailydash_seats_union` | SN daily seat metrics (paid/free flag) |
| `prod_foundation_tables.dim_member_all` | Member profile enrichment |
| `u_ir2fake.fake_romance_union` | Known fake romance accounts |

## Investigation Queries

The SQL for all queries below lives in the **`sn-seats`** action skill. Invoke that skill and use the named query listed for each step.

### 1. SN Contract Fanout
**Action:** `sn-seats` → *SN Contract Fanout*
- Params: `{START_DATE}` — start of the date range
- Use to find contracts with 15+ members, indicating potential abuse clusters

### 2. Free Trial Abuse Detection
**Action:** `sn-seats` → *Free Trial Abuse Detection*
- No required params (uses last 180 days by default; adjust as needed)
- Use to find fake romance accounts on active free SN trials

### 3. SN Member Profile Enrichment
**Action:** `sn-seats` → *SN Member Profile Enrichment*
- Params: `{CONTRACT_ID}` — the SN contract ID
- Use to enrich contract members with profile data, filtering for suspicious email domains

### 4. Name Change Detection in SN Contracts
**Action:** `sn-seats` → *Name Change Detection in SN Contracts*
- Params: `{CONTRACT_IDS}` — comma-separated list of contract IDs
- Use to find members who changed both first and last name (identity evasion signal)

### 5. Recruiter ATO with InMail UMI
**Action:** `sn-seats` → *Recruiter ATO with InMail UMI*
- Params: `{START_DATE}` — start of the date range
- Use to measure InMail damage from compromised recruiter accounts in a 7-day window

## Tips

- SN seat roles: `lssAdminSeat`, `salesSeatTier1`, `salesSeatTier2`
- Free trial detection: join with `u_metrics.lss_dailydash_seats_union` where `paid_flag = 'free'`
- Name change (reg vs current) is a strong evasion signal in SN abuse
- Contract-level analysis: cluster by `contract_id` to find organized abuse
- Common FR email domains in SN: `@hotmail.com`, `@outlook.com`, `@mail.com`, `.ru`
- Recruiter ATO UMI: use 7-day window from `u_metrics.ato_volume_union` + `abuse_damage_ato_union`
