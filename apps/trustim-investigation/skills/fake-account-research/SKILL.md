---
name: fake-account-research
description: >-
  Investigate fake account clusters including fake romance, bcookie fanout, name change detection,
  and FA overlap analysis. Use when researching fake account waves or romance scam patterns.
allowed-tools: Bash
---

# Fake Account Research

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

Other headless accounts: `tdsfake`, `trustim`, `ir2ato`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking_column.registrationEvent` | Registration details for cluster analysis |
| `tracking.scoreeventforregistration` | **Preferred** for registration scoring — pre-filtered, leaner and faster |
| `tracking_column.scoreEvent` | All scorer types (use only when JOINing with other columnar tables) |
| `data_derived.member_restrictions` | Restriction status and reasons |
| `prod_foundation_tables.dim_member_trust_restrictions` | Trust restriction details with dates |
| `u_metrics.fake_account_union` | Known fake account dataset |
| `u_metrics.member_handles_union` | Member handle/email data |
| `tracking.memberaccountchangeevent` | Name changes, email changes |

## Investigation Queries

### 1. Fake Romance Cluster by Email Pattern
**Action:** `registration-events` → *Fake Romance Cluster by Email Pattern*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Adjust the `regexp_like` pattern to match the current FR email pattern under investigation

### 2. BCookie Fanout Analysis
**Action:** `device-fingerprint` → *BCookie Fanout from Registration Events*
- Params: `{START_DATE}`, `{END_DATE}` — the date range; `{SCHEMA}` — headless schema with suspicious bcookie table
- Use to find all member registrations reusing attacker browser cookies

### 3. Name Change Detection for Fake Accounts
**Action:** `account-activity` → *Name Change Detection for Fake Accounts*
- Params: `{START_DATE}` — start of the date range; `{SCHEMA}` — headless schema with suspected FA MID table
- Use to track identity evasion via name changes post-registration

### 4. FA Cluster Overlap Analysis
**Action:** `account-activity` → *FA Cluster Overlap Analysis*
- Params: `{SCHEMA}` — headless schema with new cluster table
- Use to check how much of a new cluster is already in the known fake account dataset

### 5. Restriction Status for Suspected FAs
**Action:** `member-lookup` → *Bulk Restriction Check*
- Params: `{SCHEMA}` — headless schema; `{MID_TABLE}` — table of suspected FA member IDs
- Use to measure how many suspected FAs are already restricted vs not yet actioned

### 6. Fake Romance Login Activity from Suspicious IP Orgs
**Action:** `login-score-events` → *Fake Romance Login from Suspicious IP Orgs*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to track ongoing FR login activity hitting known friction rules

### 7. Device Fingerprint Clustering
**Action:** `device-fingerprint` → *Device Fingerprint Clustering for Known Members*
- Params: `{START_DATE}` — start of the date range; `{SCHEMA}` and `{MID_TABLE}` — suspected FA member set
- Use to identify shared canvas hash signatures within a suspected FA cluster

### 8. IP-Based Fanout for FA Clusters
**Action:** `device-fingerprint` → *IP-Based Member Fanout*
- Params: `{IP_PREFIX}` — the suspicious IP prefix to search
- Use to find all members on a suspicious IP range and check restriction rates

### 9. ASTA Restriction Results
**Action:** `account-activity` → *ASTA Restriction Results*
- Params: `{BATCH_NAME}` — the ASTA batch job name
- Use to check outcomes of an automated restriction batch job

### 10. Mass Invitation Sender Detection (FA Signal)
**Action:** `invitation-scoring` → *Mass Invitation Sender Detection via InvitationScoreEvent*
- Params: `{START_DATE}` — start of the date range; `{SCHEMA}` and `{MID_TABLE}` — suspected FA member set
- Use to find FAs sending 50+ invitations from the suspected FA set

## Tips

- Fake romance attacks commonly use `@outlook.com`, `@hotmail.com`, `.ru` email domains
- Adobe cookie pattern (AMCVS/AMCV) is a strong fake romance signal — see suspicious-registrations skill
- BCookie fanout is key for linking attacker sessions across multiple accounts
- Always check restriction status to measure impact of existing defenses
- Use `u_metrics.fake_account_union` as ground truth for known fake accounts
- Canvas hash clustering is a primary method for identifying shared device signatures across FAs
- RTT > 199ms indicates proxy usage — common in organized FA operations
- ASTA (Automated Short-Term Action) results in `u_far.irasta_results`
- Connection data: `prod_conns.connections` for second-degree fanout analysis

## Additional Tables (from MCP: unified-trust-features-lib)

The `antiabusefeaturematrix` Venice store has 278+ features available for member scoring:
- `antiabusefeatures_member_corpFeatures_hasConfirmedCompanyEmail` — corporate email confirmation
- `antiabusefeatures_member_m2mBlockFeatures_*` — block features (numBlockers, firstBlockTime)
- `u_fakeacct_sad_fakes_score_snapshots_*` — SAD fake scores
- `u_faux_member_deepfake_score_*` — Deepfake detection scores
- `u_secaggs_profileAndRiskFeatures_*` — Profile risk features (18 features)
- `u_secaggs_reportspam30daysafterreg_*` — Reports within 30 days of registration (20 features)
- `data_derived.securitylabels_fakeaccounts` — Fake account security labels

## Fake Account Appeal Flow (from MCP: appeals-service)

When a member is restricted for fake account, they can appeal by submitting ID verification documents. The appeal is reviewed by LinkedIn reviewers (OSC or Workbench). Based on the information:
- **Approve**: Remove restrictions
- **Reject**: Restriction stays

Track appeals via `u_metrics.account_appeals_union` and IDV events via `tracking.idverificationv2event`

## Playbook Investigation Flows (from im_playbooks)

### FA DIHE Investigation (FA_DIHE_investigation.ipynb)
DIHE (Detected Inauthentic Harmful Experience) replaces UMI as the primary metric.
1. Calculate weekly DIHE using `u_metrics.account_abuse_harmful_experience_union`
2. Analyze DIHE by restriction source (catch mass actions)
3. Break down harm types: invitation spam, messages, profile views
4. Analyze product & surface breakdown
5. Account analysis: restriction status, registration timeline, email domains, geography
6. Active vs passive harm analysis
7. Harm intensity distribution — identify super-spreaders vs distributed
8. **Thresholds**: DIHE > 55M, 20% WoW increase, 30% Wo3W increase
9. **Decision**: High mass action count (>1000) = coordinated defense; mostly unrestricted = ongoing attack

### FA Metrics Triage (FA_metrics_triage.ipynb)
1. Create weekly UMI table (accounts with >100 victims in 7 days)
2. Plot 3-month UMI trend
3. Analyze by restriction source and mass action breakdown
4. Split by damage type (invitations, messages, profile views)
5. Premium signup analysis — free trial abuse via `u_metrics.premium_new_signups_v4_union`
6. Handle change analysis (CREATE, DELETE, UPDATE events)
7. Top abusers by invitation/message volume
8. Name change vs registration name analysis
9. **Decision**: Damage type >80% one type = targeted attack; free trial + premium = LSS abuse; >1000 unique victims from one abuser = super-spreader

### Cross-Playbook Investigation Pattern
1. **Baseline Comparison** — Current period vs overlay (7 days ago)
2. **Attribute Clustering** — Identify shared characteristics (IP, UA, email, canvas hash)
3. **Victim Scale** — Measure unique members impacted (UMI/DIHE)
4. **Behavior Analysis** — Post-event actions (handle changes, profile edits, messaging)
5. **Rule Coverage** — Evaluate existing defense effectiveness
6. **Decision Tree** — Train on positive/negative samples to generate new rules

## 3P ID Reuse Attacks

Third-party identity providers (Google, Facebook) can be exploited to create multiple fake LinkedIn accounts from a single 3P user ID.

### Google ID Reuse
- Table: `tracking.loginevent` — look for the same `thirdpartyuserid` mapping to multiple LinkedIn MIDs
- Filter: `loginmethod = 'GOOGLE_ID_TOKEN'`
- Abuse thresholds: >2 MIDs per 3P user ID = abuse (96.5% precision); 3+ MIDs = 99.92% precision
- Nebula counter: `SUCCESSES_MID_PER_THIRD_PARTY_USER_ID`
- Top abused email domains: yahoo.com, hotmail.com, comcast.net

### Facebook ID Reuse
- Attackers shifted from Google to Facebook after Google defenses were deployed
- Filter: `loginmethod = 'FACEBOOK_ID_TOKEN'`
- Abuse threshold: >=4 MIDs per 3P user ID
- Note: Was previously misclassified as "1p" in metrics

### Kill Chain
PWR (Password Reset) → add new email → configure 2FA → change primary email

### References
- [3P ID reuse (Google)](https://docs.google.com/document/d/1yS8LmukPSDqe93TKBTZiTsT3K7KlmGhiMQ8CeJYCN-c/edit)
- [Facebook ID reuse](https://docs.google.com/document/d/1a3pZGqb2GXNN2qkSuNS34jlP1njH0NC4izVV4PjIoBo/edit)

## LoginWithProfile (LWP) Abuse

A 5-year-old legacy rule allowed challenge-free login when landing on a profile URL, which was exploited at scale to create fake accounts.

- Detection query filter: `element_at(params, 'loginWithProfile') = 'true'`
- Spoofed User Agents: Chrome 102 (Windows 10 + Windows 11 only)
- Page key: `pagekey = 'd_checkpoint_lg_floe_member_login_screen'`
- Scale: 2.67M fake accounts identified
- Registration email signal: gmail.com addresses that bounced (hard bounce)

### References
- [LWP abuse investigation](https://docs.google.com/document/d/1wxmCYdsxQ3401wYWTgJOkWRL75E6G_LXfAITz4McswQ/edit)
- [Retro cleanup](https://docs.google.com/document/d/1ee5hv82dtrpBxNjvZ6QBPgqGDOJmS29ErQkacjHQ2PA/edit)

## Workplace Email Verification (WEV) Abuse

Compromised or rented corporate email domains are used to pass workplace email verification, making fake accounts appear legitimate.

- Known abused domains: stellium.com, skill-lync.com, ethiotelecom.et, pel.com.pk, accenture.com
- 92% of restricted WEV-verified accounts were created after 2025
- Pattern: .edu domains used as primary email with a mismatched WEV corporate domain

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `DiheWidget` | `DiheWidget(account_type="fake", period="7d")` | DIHE breakdown by harm type, product, geography, active/passive for fake accounts |
| `SurfaceVisualizationWidget` | `SurfaceVisualizationWidget(start_date="2026-03-01", end_date="2026-03-14", prompt="top 10 countries hourly line chart")` | Registration traffic visualization with NL filtering (country, OS, device, org, chart type) |
| `SevCalculatorWidget` | `SevCalculatorWidget(cohort_member_ids="SELECT mid FROM ...")` | Automated SEV assessment for FA cohort (DIHE + scraping WoW with charts) |

## Related Repos
- `fake-account-member-scoring-proml` — FA scoring models (Account Abuse AI)
- `account-abuse-holistic-detection` — Holistic detection (Account Abuse AI)
- `appeals-service` — FA appeal flow with IDV
