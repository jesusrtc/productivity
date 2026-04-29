---
name: payment-investigation
description: >-
  Investigate payment abuse cohorts using purchase scorer events. Covers payment ID sharing
  across members, member PID density, transaction type analysis, country code mismatch
  detection, and decline history patterns. Use when investigating payment fraud, card testing,
  stolen card rings, or ads abuse via post-payment authorization.
allowed-tools: Bash
---

# Payment Abuse Cohort Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by country, signal tier, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user

### Presentation Rules

1. **Raw data first, then summaries.** After every query, present the raw result rows to the user before any aggregated or summary tables. The user must see the source data before your interpretation.
2. **Evidence-backed assertions only.** Never state a conclusion (e.g., "this is an ATO ring", "defenses are failing") without citing the specific data that supports it — exact field values, member IDs, and counts from query results. Example: "MID 479795285 has `loginRestrictRequired=true` but `is_restricted=null` — the restriction flag fires but doesn't execute."
3. **RCHARGE requires success/decline context.** Whenever presenting RCHARGE data, always include `declined_recrs_180d` and `successful_recrs_180d` alongside the RCHARGE count. A high RCHARGE with 0 successful and many declined is a very different signal than RCHARGE with successful charges.

Use the Captain MCP `execute_trino_query` tool to run these queries on the **holdem** server.

**Always include this preamble:**
```sql
SET SESSION li_authorization_user = 'trustim';
```

**Partition format:** `YYYY-MM-DD-00` (e.g., `2026-03-20-00`)

## Important: False Positives

> ### Corporate Card False Positives
> **Shared payment IDs do not always indicate abuse.** Corporate/company cards are legitimately shared across multiple employees (e.g., a marketing team sharing a corporate card for LinkedIn Ads). Before flagging a PID or member cohort as abusive, verify at least one of the following corroborating signals:
> - **AUTH-only pattern** — high AUTH count with zero DEBIT/RCHARGE. AUTH-only has multiple explanations: corporate cards staging for campaigns, legitimate cards whose MIT charges fail at the issuer, or abusers prepping accounts for future waves of purchase abuse. AUTH-only alone is ambiguous — it becomes a stronger abuse signal only when combined with other indicators below.
> - **Country code mismatches** — IP geo diverges from billing/bank country (proxy or stolen card)
> - **High decline history** — elevated `declined_recrs_180d` with zero `successful_recrs_180d`
> - **Rapid PID cycling** — a single member burning through many PIDs in a short window
>
> PIDs with only DEBIT/RCHARGE transactions across members in the same billing country and consistent geo IPs are likely legitimate corporate cards and should be deprioritized.

> ### New Account False Positives
> **A new account with 1-2 AUTH PIDs alone is NOT sufficient to conclude abuse.** New users legitimately add payment methods when signing up for LinkedIn Ads or Premium — this is normal onboarding behavior. Only flag a new account as suspicious when AUTH-only activity is combined with **at least one** corroborating signal:
> - **High PID density (3+)** — legitimate users don't cycle through many cards on day one
> - **Country code mismatches** — IP geo diverges from billing/bank country
> - **PIDs shared with other flagged members** — the PID appears in the cross-member linkage results
> - **`PID_fake_accounts > 0`** — the PID is already associated with known fake accounts
> - **`accountLabel = FAKE`** — the system has independently classified the account as fake
> - **Elevated decline history** on the PID — `declined_recrs_180d` with zero `successful_recrs_180d`
> - **0 connections + `spamRestrictRequired = true`** — empty profile with spam signals
>
> The more signals that converge on a single member, the higher the confidence. A single signal in isolation (especially just AUTH + new account) should be treated as low confidence and not flagged without further investigation.

## Background

This investigation targets payment abuse cohorts. Common attack patterns include:
- **Card sharing rings** — a single payment ID used across many member accounts
- **Card testing/cycling** — a single member burning through many payment IDs with high AUTH counts but no successful charges
- **Post-payment ads abuse** — abusers authorize a card, post malicious ads, then let the payment decline (exploiting the post-payment nature of LinkedIn Ads)
- **Country code mismatches** — IP geo, billing country, and bank country diverging, indicating stolen cards or proxy usage

**Transaction types to understand:**
- `AUTH` — card authorization, processed as a **customer-initiated transaction (CIT)**. Multiple AUTH events can appear for the same paymentId (even across different memberIDs) without representing distinct user-initiated card additions. High AUTH count alone does not prove card testing — require corroborating signals.
- `PREAUTH` — pre-authorization hold.
- `DEBIT` — actual charge collected. This is revenue-impacting.
- `RCHARGE` — recurring charge attempt, processed as a **merchant-initiated transaction (MIT)**. Subject to different issuer risk controls than AUTH/CIT. A card can legitimately pass AUTH but fail all RCHARGE attempts due to issuer MIT-specific rules, funds availability, or account-level restrictions.

**CIT vs MIT distinction:** The initial authorization (AUTH) is generally a customer-initiated transaction, while subsequent Ads charges and retries are merchant-initiated. Issuers apply different risk controls to each type. As a result, AUTH success alone is not a sufficient trust signal for card reuse or ongoing Ads payment flows. Decisions around reuse across members rely on broader signals including downstream MIT outcomes and prior risk indicators — not AUTH in isolation.

**Note:** DEBIT and RCHARGE represent actual revenue collection. AUTH-heavy patterns with no successful charges *may* indicate abuse but also have legitimate explanations (MIT failures at the issuer). Always triage the decline reason before concluding abuse.

**Decline reason categories — critical for interpretation:**
1. **LinkedIn-side blocks:** When a member is restricted, the rule `block rcharges for login restricted members` intentionally blocks all payment attempts. Check `isLoginRestrictRequired` in the Account Risk Profile.
2. **PID blocklisted:** A failed recurring charge may result in the PID being auto-blocklisted under `PaymentID Reputation based Rules`, or manually blocked by PAT. Once blocklisted, any future attempt using that PID — including on other member accounts — will be declined. Check `PID_PID_Reputation_label`.
3. **Issuer/processor declines:** Insufficient funds, issuer MIT-specific risk controls, general declines. These are external rejections. The PID may not be blocklisted and could still be used on other accounts if subsequent signals improve.

## Investigation Flow

### 1. Clarify Scope
Ask the user:
- **Date range** — "What date range should I investigate?" (`{START_DATE}` to `{END_DATE}`)
- **Investigation focus** — "Are you looking at shared payment IDs across members, members with too many cards, or both?"
- **Transaction types** — "Should I include all transaction types or focus on AUTH/PREAUTH only?"
- **Threshold** — "What's the minimum linkage to flag? (default: 2+ members per PID, or 2+ PIDs per member)"

### 2. Payment ID Cross-Member Linkage
**Action:** `payment-events` → *Payment ID Cross-Member Linkage*
- Params: `{START_DATE}`, `{END_DATE}`, `{MIN_MEMBERS}` (default: 2)
- Start here to find payment IDs shared across multiple members
- A PID on multiple members is not automatically suspicious — check whether the PID is blocklisted (`PID_PID_Reputation_label`) or if prior failures were due to temporary factors (issuer MIT declines, account-level restrictions). Only blocklisted PID reuse is a strong abuse signal.
- Look for PIDs with high `auth_count` but zero `debit_count` / `rcharge_count` — *may* indicate card testing but also has legitimate explanations (MIT failures). Require corroborating signals before concluding abuse.
- Check `declined_recrs_180d` vs `successful_recrs_180d` — high decline ratio is notable, but triage the decline reason: LinkedIn-side blocking (`isLoginRestrictRequired`), PID blocklist, or issuer/processor rejection.
- Flag any country code mismatches (IP vs billing vs bank)

### 3. Member Payment ID Density
**Action:** `payment-events` → *Member Payment ID Density*
- Params: `{START_DATE}`, `{END_DATE}`, `{MIN_PIDS}` (default: 2)
- Use to find members cycling through many payment instruments
- High PID density (6+) is a strong fraud signal
- Cross-reference members found here with PIDs from step 2 to identify full abuse rings

### 4. Member Account Risk Profile
**Action:** `payment-events` → *Member Account Risk Profile*
- Params: `{START_DATE}`, `{END_DATE}`, `{MEMBER_IDS}` (from steps 2 and 3)
- Run against the suspicious members identified in steps 2 and 3
- Check `PID_is_corporate_card` first — if `true`, deprioritize (likely legitimate)
- Check `PID_fake_accounts` and `PID_historical_atos` — non-zero values confirm the PID is circulating in known abuse/ATO rings
- Compare `account_age_days` with `profile_accountAgeInDays` for consistency
- New accounts with `PID_fake_accounts > 0` and no restriction = fake accounts slipping through
- New accounts with 1-2 PIDs and no other signals = **likely legitimate, do not flag** (see False Positives section)
- Established accounts with `PID_historical_atos > 0` and `isLoginRestrictRequired = true` = likely ATO
- Check `is_currently_restricted` and `restriction_reasons` to see if defenses already caught them

### 5. Decline Reason Triage
Before assembling the abuse cohort, triage the decline reasons for flagged PIDs/members. This step prevents misclassifying LinkedIn's own defenses or legitimate issuer declines as abuse signals.
- **Check `isLoginRestrictRequired`** from the Account Risk Profile: if `true`, high RCHARGE declines are expected — LinkedIn's `block rcharges for login restricted members` rule is intentionally blocking charges. This is defense working as designed, not an independent abuse signal.
- **Check `PID_PID_Reputation_label`**: if the PID is blocklisted (auto under PaymentID Reputation based Rules or manual by PAT), all future attempts on any member will be declined. Cross-member PID reuse with a blocklisted PID is a strong abuse signal.
- **Check activated rules**: Use `rule-performance` action to query `scoreevent_activated_rule` for the specific rules `block rcharges for login restricted members` and PaymentID Reputation rules against the flagged PIDs/members. This tells you definitively whether LinkedIn's rules caused the declines.
- **Remaining declines** (not explained by LinkedIn rules or PID blocklist) are likely issuer/processor rejections — insufficient funds, MIT-specific risk controls, general declines. These are weaker abuse signals on their own.

### 6. Cross-Reference and Cohort Assembly
After running queries from steps 2-5:
- Identify members that appear in **both** result sets (member has many PIDs AND those PIDs are shared with other members)
- Look for geographic clustering in the `billing_countries`, `bank_countries`, and `geo_ip_countries` columns
- Check for AUTH-only patterns: members/PIDs with high `auth_count` but zero `debit_count` and `rcharge_count`. Remember that AUTH-only has legitimate explanations (MIT failures at issuer) — it becomes a strong signal only when combined with other indicators.
- Assess the `payment_signal` column to prioritize: High > Elevated > Low
- Use the account risk profile to classify members as fake account, ATO, or legitimate
- Use the decline reason triage from step 5 to distinguish "LinkedIn defenses working" from "active abuse pattern"
- **Deprioritize single-signal members.** A member that only appears in one query with low PID density (1-2) and no corroborating signals (no IP mismatches, no PID reputation flags, no `accountLabel = FAKE`) is more likely a legitimate user than an abuser. Focus investigation time on members with **converging signals** — multiple independent indicators pointing to abuse

### 7. Assess Impact and Conclude
- Quantify the cohort: how many members, how many PIDs, what transaction volume?
- Determine if this is an active campaign (recent AUTH spikes) or historical
- Check if any DEBIT/RCHARGE transactions succeeded (revenue impact)
- Document findings in the audit trail with exact query results
