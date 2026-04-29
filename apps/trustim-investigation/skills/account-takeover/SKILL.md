---
name: account-takeover
description: >-
  Investigate account takeover (ATO) incidents using Trino queries. Covers login analysis,
  MITM/phishing detection, session hijack, credential washing, password invalidation, and
  IP washing patterns. Use when oncall for ATO spikes or login anomalies.
allowed-tools: Bash
---

# Account Takeover Investigation

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema — columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII — aggregate by IP org, email domain, country, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
7. **If a table is not found or access is denied:** try the headless account alternatives listed below. If still inaccessible, search for an equivalent table containing the same key columns (e.g., `SHOW TABLES IN {schema} LIKE '%keyword%'`) or ask the user for an alternative data source. Tables in `u_*` schemas are user-created staging tables that may be deprecated.

## Agent Context

You are an experienced trust investigator/agent who is helping answer inquiries and performing analysis on LinkedIn's Trust and Safety issues on account security.

The questions might or might not be related to Trust and Safety depending on the context and user's perception of this area. Trust and Safety is a broad area that includes account security, like account takeovers, fake accounts, user reports, and content moderation.

You will be provided with context from LinkedIn's trust datasets, which contains information about various events such as login, password reset, general account activity, or other trust-related events. The data may include information such as IP addresses, member IDs, timestamps, and other relevant fields. You will also be provided with a dump of the data retrieved from the SQL query and clustering — use the query and the data provided to answer the user's inquiry. Commonly to identify an issue with the account or to explain the data that you see.

If you can make a conclusion based on the data, do so. If you cannot, explain why. If there is not sufficient data, explain why and what additional information would be needed. Do not include anything that you are not certain about and can logically deduct. If anything is unclear, state that it is a hypothesis or theory in the summary text.

**Your answers should be two parts:**
1. **Summary** — concise and to the point. Give a confidence level: "high confidence", "medium confidence", or "low confidence".
2. **Explanation** — detailed reasoning with assumptions, data limitations, and additional helpful context.

### ATO Determination

To determine ATO, check these entry points:

**ATO via password reset:**
Bad actor has access to the email account and can reset the password.

**ATO via login:**
Bad actor has the member's login credentials. Can also use third party logins (Google) if the member linked their account — no password needed.

**ATO via session:**
Bad actor hijacks the user's session. Look for session ID reuse across multiple IP addresses/locations, or sessions active from unusual locations/devices.

**Account rentals:**
Users willingly give account access to bad actors who pay to keep the account unrestricted, including performing ID verification then returning the account.

**ATO via "Not Me" PWR Bypass:**
Bad actors exploit the "not me" link in Email Pin Challenge (EPC) during handle-add flow to trigger a password reset that bypasses PWR scorer entirely (no PRSE fires). 40% of ATOed accounts from self-reports were eligible for SHC but never got it due to this gap. Chain: Google 3P login → handle add → EPC → click "not me" → PWR without scoring. Reference: [PWR via "Not Me" flow](https://docs.google.com/document/d/1Mi8DSwrII7apbdiXOUL7Oj2JiKuvmdQ1KNENkTXzvV8/edit)

**ATO via Close/Reactivate Abuse:**
Bad actors: PWR via email → add new email (Outlook/Hotmail) → set as primary → close account (within 5-20 min) → reactivate 1-14 days later. Account closure deletes all non-primary handles — this is the design flaw. 77% target old accounts (1+ yr inactive), 20% from Vietnam IPs. ~3000-3500 daily volume; self-reports: 20-35/day. Table: `tracking.accountmanagementevent` — `action = 'CLOSE_ACCOUNT'` / `'REACTIVATE_ACCOUNT'`. Reference: [Close/reactivate abuse](https://docs.google.com/document/d/1t4U4bbM3x6wxyVwPCSeGvJuD-myeJQUOvFNVidd0IZc/edit)

**ATO via OTP-to-PWR Bypass:**
OTP login resets the dormancy counter, bypassing the Code Red IDV rule (`activityStatistics: numDaysSinceLastActivity >= 6*365`). Two OTP flows exploited: login page OTP and FastTrack OTP (`parentpagekey = p_checkpoint_lg_consumerLoginWithProfile`). ~12k/day ATO rate, 400k accounts identified. Table: `tracking.logintokenlifecycleevent`. Reference: [OTP ATO](https://docs.google.com/document/d/1xjxPjssQCDHJamFAgIOzgbf_fNOmrI2vypSmQN_9fFo/edit)

**ATO via Expired Domain:**
Bad actors purchase expired email domains → PWR to gain access to accounts using those domains → submit fraudulent ATO self-reports. Targets Code Red accounts inactive 5+ years. Detection: check `host -t MX DOMAIN_NAME_HERE` for missing MX records; shared TXT record fingerprints. >90% of unrestricted accounts were unrestricted by RPA/Harmony bot without IDV. Reference: [Expired-domain ATO](https://docs.google.com/document/d/1Lw63xMIMKFw55e6ZIWaZBOsHeS8BlqLsVbpsnbVyXmg/edit)

**ATO via 3P Login (Google, Facebook, Microsoft):**
- Google: same `thirdpartyuserid` cycling through multiple email handles. Threshold: >2 MIDs = abuse (96.5% precision at 2+, 99.92% at 3+).
- Facebook: attackers shifted to FB after Google defenses deployed. Threshold: >=4 MIDs. FB logins were misclassified as "1p" in metrics.
- Microsoft: `element_at(params, 'authType') = 'MICROSOFT_LOGIN'`. 40% of ATO self-reports are MSFT 3P. 2.3x volume increase since Jun 2025.
- Nebula counter: `SUCCESSES_MID_PER_THIRD_PARTY_USER_ID` in `ONE_DAY` bucket
- References: [3P ID reuse](https://docs.google.com/document/d/1yS8LmukPSDqe93TKBTZiTsT3K7KlmGhiMQ8CeJYCN-c/edit), [Facebook 3P](https://docs.google.com/document/d/1a3pZGqb2GXNN2qkSuNS34jlP1njH0NC4izVV4PjIoBo/edit), [MSFT 3P](https://docs.google.com/document/d/1gzKg_DJrVNTfw1mn9JLG89FTOzBYDBBV-gnjJctYXsg/edit)

**ATO via SSP Bypass (Android Login):**
Bad actors login via Android native app to generate SSP-eligible session, then use it to bypass PWR SSP. Reference: [ATO Trends](https://docs.google.com/document/d/1sBm3kDTGX6Ld1CSb7jtwI68N6my6p9naA33avGE7Ijc/edit)

Check for inconsistencies: multiple logins from different IPs/locations, unusual activity not consistent with normal behavior.

### ATO Self Reports

An ATO self report is when a user suspects their account was hacked. LinkedIn has a TS-RHA form (https://www.linkedin.com/help/linkedin/ask/ts-rha) for users to report account takeover for account recovery.

### CS Audit Log Analysis

When provided with CS audit log data, analyze using these field mappings:
- `acting_member_id` — member ID of the user
- `event_type` — event performed
- `event_mode` — user-performed or system event
- `notes` — additional notes
- `browser_id` — cookie tracking web activity
- `session_id` — session in which the event occurred
- `user_agent` — browser user agent string
- `ip_address` — IP address of the event
- `ip_org` — organization associated with the IP
- `ip_country` — country associated with the IP
- `event_time` — timestamp of the event

### Incident Promotion

An alert can be promoted to an incident when the data shows abuse that needs further research. Guide the user to reach that conclusion by providing details and enrichment from the data.

---

Use the Captain MCP `execute_trino_query` tool on **holdem** server.

**Preamble:** `SET SESSION li_authorization_user = 'ir2ato';`

Other headless accounts: `trustim`, `login`

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking.loginevent` | Raw login events |
| `tracking_column.scoreEvent` | Login scorer decisions (SCORER_LOGIN) |
| `tracking.scoreevent` | Score events with params and counterinfo |
| `data_derived.member_restrictions` / `prod_foundation_tables.dim_member_trust_restrictions` | Restriction status |
| `tracking.securitychallengeevent` | Challenge events (email pin, SMS, SSP) |
| `tracking.userrequestdenialevent` | Request denial events |

## Investigation Queries

### 1. Login Score Event Analysis
**Action:** `login-score-events` → *Login Score Event Analysis*
- Params: `{DATE}` — the target date
- Use to get a breakdown of login decisions by app type, password result, and challenge type

### 2. MITM/Phishing ATO Detection
**Action:** `login-score-events` → *MITM/Phishing Rule Detection*
- Params: `{DATE}` — the target date
- Use to detect login sessions flagged by MITM/phishing rules (Linux X11, Evilginx, ColorFish)

### 3. Credential Washing Detection
**Action:** `login-score-events` → *Credential Washing Detection*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to track logins hitting the credential washing rule over a date range

### 4. IP Washing / Session Hijack Analysis
**Action:** `login-events` → *IP Washing Login Correlation*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to find logins from IPs in the tainted IP list; update `u_ir2ato.tainted_ips` as appropriate

### 5. RuleSetType_GENERIC_exception Analysis
**Action:** `login-score-events` → *RuleSetType_GENERIC_exception Detection*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to detect ATO from drools failing open; elevated rates indicate a defense gap

### 6. Login Counter Analysis
**Action:** `login-score-events` → *Login Counter Analysis*
- Params: `{DATE}` — the target date
- Use to examine login counter distributions for credential stuffing signals

### 7. Password Reset Abuse
**Action:** `login-score-events` → *Password Reset Abuse via Score Events*
- Params: `{START_DATE}` — start of the date range
- Use to track ONE_TIME_PASSWORD_LINK logins over time for ATO via email compromise

### 8. 2FA Opt-in After ATO
**Action:** `account-activity` → *2FA Opt-in After ATO Correlation*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` to the headless schema with the ATO MID table
- Use to measure what fraction of 2FA enrollments are ATO-correlated

### 9. Device Fingerprint Clustering for ATO
**Action:** `device-fingerprint` → *Device Fingerprint Clustering by Canvas Hash*
- Params: `{START_DATE}` — start of the date range
- Use to identify shared device signatures across compromised accounts; RTT > 199ms indicates proxy

### 10. Self-Report Correlation
**Action:** `account-activity` → *Self-Report Correlation for ATO*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` to the headless schema with suspected ATO MIDs
- Use to correlate suspected ATOs with TS-RHA self-reports

### 11. Phishing IP Bcookie Fanout
**Action:** `device-fingerprint` → *Phishing IP Bcookie Fanout from Login Events*
- Params: `{START_DATE}` — start of the date range; `{PHISHING_IP}` — the known phishing IP
- Use to find all bcookies used from a phishing IP, then all members who used those bcookies

## Playbook Investigation Flows (from im_playbooks)

### ATO UMI Triage (pb_ato_umi.ipynb)
1. Replicate weekly ATO UMI spike from alert using `u_metrics.abuse_damage_ato_union`
2. Identify spike week vs reference week — compare unique victim counts
3. Find top UMI contributors (abuser_id with highest victim_id count)
4. Check restriction sources via `u_metrics.restriction_appeal_union` (model vs manual)
5. Enrich accounts: name changes (reg name vs current), IP country mismatches, email domain concentration
6. **Decision**: High UMI WoW + name changes + country mismatches = ATO campaign

### PWR + EPC Triage (pb_pwr_with_only_epc_triage.ipynb)
1. Get daily PWR (password reset) with EPC (email PIN challenge) success rates
2. Compare current day vs 7-day overlay baseline
3. Check for secondary/primary handle changes within 15-day window post-PWR
4. Check 2FA changes via `tracking.TwoStepOptinEvent`
5. Verify IP country mismatch signals
6. Calculate SHC/SSP challenge ratios using IQR method
7. **Decision**: High PWR + EPC + low secondary handle challenge rate = ATO attempt
8. **Threshold**: Challenge ratio below Q1 - 1.5*IQR = defense gap

### Phishing SmartLink Investigation (Phishing_SmartLink.ipynb)
1. Validate UMI spike, find top contributors
2. Find SmartLinks clicked by top contributors via `prod_salesmessaging.bundle`
3. Fetch SL metadata (creator, content type)
4. Find all members who clicked identified SLs via `tracking.salesbundleassetviewevent`
5. Check hostname mismatches in DF data (not linkedin.com/linkedin.cn = MITM)
6. Canvas hash clustering — centralized tool = MITM proxy
7. Screen resolution aspect ratio analysis — non-standard ratios (not 1.19/1.25/1.33/1.6/1.78) = noVNC
8. IP fanout to find all compromised accounts
9. **Decision**: Hostname mismatch + canvas hash cluster + non-standard aspect ratio = organized MITM attack
10. **Coverage**: Rule coverage = (blocked by MITM rule) / (total hostname mismatches with DF)

## Full Member Investigation Workflow

For a comprehensive per-member ATO investigation, follow these steps in order (reference: `account-takeover-ai-agent-skills` repo):

1. **Member Profile & ATO Label** — `prod_foundation_tables.dim_member_all` JOIN `prod_foundation_tables.fact_ato_mids`
2. **Login Activity Timeline** — `pv_aggregate.member_aggregate` (IP, country, UA, dates)
3. **IP Proxy/Hosting Check** — `data_derived.georeputation_ipreputation` (`isownedbyhostingservice`, `isproxy`)
4. **DFP Bot Score** — `tracking.AntiAbuseJavaScriptDeviceFeaturesDFPWebEvent` (`enrichment.bot.scorevalue`, `hostingfacility`, `ipRoutingType`)
5. **Session Replay Detection** — `prod_custservice_column.cs_audit_log_entries` (same session ID, different browser family on different dates)
6. **CS Audit Log Events** — Key events: `SHOWN_ATO_SUPER_CHALLENGE`, `CHANGE_PASSWORD_FROM_EMAIL`, `CONFIRM_EMAIL_ADDRESS`, `UPDATE_PRIMARY_EMAIL`, `ID_VERIFICATION_CALLBACK_RESPONSE`
7. **2FA Status** — `prod_auth.two_step_opt_in` (`authenticator_method`, `two_step_enabled`)
8. **Bcookie Linkage** — `data_derived.pageviews_member_aggregate_column_daily` (shared browser cookie across MIDs)
9. **Device ID Linkage** — `anti_abuse_device_identification.deviceids` (shared device fingerprint)
10. **IDV Status** — CS audit log with `event_type LIKE '%id_verification_callback_response%'`
11. **Restriction History** — `data_derived.SecurityLabels_restrictionSnapshot` (login + spam restriction timeline)
12. **Registration Analysis** — `tracking.RegistrationEvent` + `tracking.scoreeventforregistration` (datacenter IP at reg = fake, not ATO)
13. **Safire Score** — `u_fakeacct_copy_from_war.SafireProML_scoresArchived` (high score + no ATO signals = fake account)
14. **Messaging Activity** — `tracking.messagesendfunneltrackingevent` + `tracking.PrivateContentScoreEvent` (spam/URL flags)
15. **Invitation Activity** — `data_derived.InvitationHistory` + `data_derived.SecurityLabels_MemberAutomationLabels_Invites`
16. **Message Automation** — `u_metrics.messages_sent_union` (inter-send time <=3s = automated)

**Headless account for full investigation:** `fakeacct`

## Phishing / MITM Investigation (Yellowfish Runbook)

Reference: [Yellowfish ATO Attack Summary and Investigation Runbook](https://linkedin.atlassian.net/wiki/spaces/ENGS/pages/525351902)

### Evilginx Detection (Definitive Signal)

The Evilginx MITM proxy sends a custom `X-Evilginx` header to phished sites. This is an easter egg in the source code. Combined with CC always being `[bcookie,bscookie]`, this is sufficient to detect all vanilla Evilginx attacks.

**Query: Track Evilginx logins via score events**
```sql
-- Join login events with score events, filter for X-Evilginx in sorted header names
SELECT le.*, se.params
FROM tracking_column.loginevent le
JOIN tracking_column.scoreEvent se
  ON le.header__memberid = se.header__memberid
  AND le.submissionid = element_at(se.params, 'submissionId')
WHERE le.datepartition >= '{START_DATE}'
  AND se.datepartition >= '{START_DATE}'
  AND le.header__memberid > 0
  AND le.loginresult = 'PASS'
  AND element_at(se.params, 'sortedHeaderNames') LIKE '%X-Evilginx%'
```

### Golden Grouper (Human-Controlled MiTM)

NOT Evilginx — static HTML/PHP pages with manual credential relay. Targets recruiter accounts.

**Detection:** 2FA solve delay >30 seconds between login and 2FA challenge (join on `submissionid`, compute `time_difference`). ~2k/month steady-state volume, >90% precision. Rule: `'IMIR: Recruiter phishing attack w/ manual intervention and delay in 2FA and form fill'`. Attackers may use residential VPNs to evade IP-based detection. References: [Golden Grouper](https://docs.google.com/document/d/1rGbWhGmYSF-AJUnonYRRoW4u0T2fdFcOWHiiWGsU4AU/edit), [Followup](https://docs.google.com/document/d/1xWWsbewsNZGrLpLSuDWVuE7IVpN3RbUmF6itsJmQLP0/edit)

### Silver Herring (VM-Based MiTM)

Remote browser sessions on VM, targeting tech executives (Sep 2025). Single machine with single canvas hash across 4 IPs/countries; uses residential proxies.

**Detection signals:**
- Unusual screen resolutions not matching standard aspect ratios (1.19/1.25/1.33/1.6/1.78)
- Software-only WebGL renderers (no real GPU) → regex: `swiftshader|subzero|0x0000c0de|basic render driver|virtualbox|vmware`
- `Frame_deviceIdSet` field mapping: `[canvasHash, webGLHash, deviceMemory, OS, platform, resolution, browserVendor, pixelDepth, colorDepth, numCores]`
- Same deviceID with multiple different resolutions = parallel sessions on single machine
- Single canvas hash across multiple IPs/countries = centralized tool

Reference: [Silver Herring](https://docs.google.com/document/d/1UWq6fZl3CDJswbtIfLCtp8WhSmmJgwAKNEcg5YR5X1M/edit)

### Smart Link Investigation Tables

| Table | Purpose |
|-------|---------|
| `prod_salesmessaging.bundle` | Smart link creation events (URLs, creator, assets) |
| `tracking.salesbundleassetviewevent` | Smart link click events (who clicked, when, IP) |
| `prod_salesmessaging.viewingsession` | Smart link view sessions |
| `foundation_lts_mp.dim_cap_seat` | Seat-to-MID lookup and recruiter status |
| `tracking.PrivateContentScoreEvent` | Hashed URI metadata for smart link content scoring |

**Key fanout queries:**
1. Find smart links created with suspicious URLs via `prod_salesmessaging.bundle` (filter `asset.field4.originalUrl` by regex)
2. Find all members who clicked bad smart links via `tracking.salesbundleassetviewevent` (filter by `requestheader.path LIKE '%smart-links/{BUNDLE_ID}%'`)
3. Join clickers with `tracking_column.loginevent` to find who was compromised (login from bad org IPs after clicking)
4. Fanout from compromised MIDs via IP org analysis to find additional ATOs

### Messaging Investigation Tools

**`limsg` CLI** (run from prod host e.g. `lor1-shell01`, SSH via LNKDPROD account + VIP):
- `limsg message-scan -f prod-lor1 -t URL_FULL -a <url>` — scan for messages containing a URL
- `limsg message-scan -f prod-lor1 -t AUTHOR -a <member_id>` — scan all messages from a member
- Requires `ina-messaging-datavault-access` group access

**HireMailbox-to-MID mapping:**
```bash
# From prod host (lor1-shell01)
curl -s "http://espresso-router-lva1.prod.linkedin.com:10880/ina-messaging-datavault/hiremailboxMemberMapping/{hireMailboxId}" \
  -H 'X-RestLi-Protocol-Version: 2.0.0' \
  -H 'X-RestLi-Method: get' | python -m json.tool
```

**Seat-to-MID lookup (recruiter status):**
```sql
SELECT member_id, contract.contract_type, is_seat_active
FROM foundation_lts_mp.dim_cap_seat
WHERE member_id IN ({MEMBER_IDS})
  AND is_seat_active = true
  AND contract.is_contract_active = TRUE
  AND account.is_account_active = TRUE
  AND is_li_seat = FALSE
```

### URL/Domain Deny List

Block phishing URLs via CSTool: `https://cstool.www.linkedin.com/cstool/allowDenyLists/SAFE_BROWSING_BLACK_LIST/edit`

Note: This blocks specific URLs, not entire domains.

### Time-to-First-Message Benchmarks (Historical Campaigns)

| Campaign | Time from ATO login to first phishing message |
|----------|-----------------------------------------------|
| PurpleDory | 14min - 45min |
| YellowFish | 11min - 2hrs |
| RedTuna | 12min - 7hrs |
| BrownGoby | 1hr - 4hrs |

## ATO Risk Signal Reference

### HIGH Severity
| Signal | Source |
|--------|--------|
| Session replay (same session ID, different browser family) | CS audit log |
| DFP: hosting=True + routing=pop + bot_score 600-800 | DFP Web Event |
| Bcookie linkage to known-bad MIDs | Pageview aggregates |
| Device ID linkage to known-bad MIDs | Device identification |
| `CHANGE_PASSWORD_FROM_EMAIL` after login from new country | CS audit log |
| `UPDATE_PRIMARY_EMAIL` event | CS audit log |

### MEDIUM Severity
| Signal | Source |
|--------|--------|
| `SHOWN_ATO_SUPER_CHALLENGE` in CS audit log | CS audit log |
| IP from hosting/datacenter only (no home/mobile IPs) | IP reputation |
| DFP: hosting=True + routing=pop + bot_score 1-600 | DFP Web Event |
| 2FA disabled/removed on previously-protected account | 2FA status |
| Old account (5+ yr) reactivated after 1+ yr dormancy | Login timeline |

### Fake Account Signals (Not ATO)
| Signal | Source |
|--------|--------|
| Safire v9_0 score > 0.981 | Safire scores |
| Datacenter/hosting IP at registration time | Registration event |
| DFP bot_score > 800 + hosting | DFP Web Event |
| Message inter-send time <=3s (recruiter) | Messages sent |

## Scorer Failure / Defense Gap Detection

### GhostLock Scorer Failures (5 failure modes)

1. **Scorer timeout** — LoginEvent fires but ScoreEvent missing. Join LE LEFT JOIN SE on submissionid to find gaps. ~82k compromised/day during failures.
2. **Missing activatedrules** — Nebula counter fetch fails, Drools can't evaluate.
3. **Cookie seen race condition** — bcookie written to MAH before scorer completes.
4. **`RuleSetType_GENERIC_exception`** — Drools fail-open, ~500 ATOs/day baseline.
5. **Missing SE but LE fired** — checkpoint proceeds before scorer finishes.

**Key detection query pattern:**
```sql
-- Find login events with no corresponding score event (defense gap)
SELECT le.*, se.*
FROM tracking.loginevent le
LEFT JOIN tracking.scoreeventforlogin se
  ON le.submissionid = element_at(se.params, 'submissionId')
WHERE le.datepartition >= '{START_DATE}'
  AND se.datepartition >= '{START_DATE}'
  AND se.submissionid IS NULL
```
Null SE rows = defense gap. References: [GL login scoring](https://docs.google.com/document/d/1ctpMWccY78s_qRe3L2rcu3hkzCARyAPCiwmPIPxZzPc/edit), [GhostLock EPC](https://docs.google.com/document/d/1QHxXeWKsHFkj5LT4KWLXrqKW74PFs-IF6YzAvhYEy6w/edit), [ASTA exceptions](https://docs.google.com/document/d/1G3wR5yjre7SGKuTqQ93GDuzkLUdLUduf1OII62RT6iI/edit)

### EPC Embedding Flaw

ML embedding-based device familiarity rule has `minimumDeviceEmbeddingDistance` null → rule doesn't fire → silent defense degradation. Reference: [EPC flaw](https://docs.google.com/document/d/1QO2xXMME6WPk0JCXCKReanAimiqJ2GO4s6gG-qYq8q0/edit)

### isASNSeen Bypass

Residential proxy ASN matches victim's historical ASN → `isASNSeen == false` not met → EPC not triggered. 12.9% of ATOs. Reference: [GhostLock EPC](https://docs.google.com/document/d/1QHxXeWKsHFkj5LT4KWLXrqKW74PFs-IF6YzAvhYEy6w/edit)

## ASTA Detection Patterns

### Superfast 2FA

2FA enrollment in ≤2 seconds = bot (100% precision, 0 FP). 25k unrestricted accounts at first detection. Generalizable to other events (handle change, profile edit). Reference: [Superfast 2FA](https://docs.google.com/document/d/1SWOG2VJ55aNQV2lUzYTQ6yQ-6pxN4PTTraJdKMEEfgw/edit)

### LCS Email Algorithm

Lowest Common Substring of old vs new email prefix < 4 characters (after removing special chars) = unauthorized email swap. Combined with UA-IP org clustering and no-tracking validation (`no-tracking=false` from `u_far_copy_from_holdem.ghost_lock_login_events`). ~500 daily restrictions, 100% precision. Tables: `tracking.memberhandlechangeevent`, `prod_handlesdb.emailurntostaticemaildatamapping`. Reference: [ASTA email change](https://docs.google.com/document/d/1bqX9FtRl2IB6P1ToSw3TuD5K7p9Ze2laJbyYZFhp12g/edit)

### GhostLock Cleanup

Detects bot-driven ATO logins using a combination of behavioral signals (not hardcoded IoCs):
- **UA pattern:** Look for `LIAuthLibrary` UAs with outdated app versions and specific device models — the ASTA job dynamically extracts suspicious UA-IP org combos from the past 2 months
- **No li/track hit:** `is_li_track_with_bcookie = False` from `u_far_copy_from_holdem.ghost_lock_login_events` — indicates headless/bot traffic
- **High IP attempt rate:** >15 distinct login attempts per IP per day

Tables: `u_far_copy_from_holdem.ghost_lock_login_events`, `u_ir2ato.daily_li_track`. Reference: [ASTA GhostLock](https://docs.google.com/document/d/1G3wR5yjre7SGKuTqQ93GDuzkLUdLUduf1OII62RT6iI/edit)

## ATO Metrics (Weekly Reporting)

For weekly ATO metrics triage, track these (reference: `account-takeover-ai-agent-skills/reporting-metrics`):

1. **ATOs Detected** — `u_metrics.ato_volume_union` (by `atosource`, `specificrestrictionsource`)
2. **Account Hacked Flags** — `u_metrics.user_flagging_union` where `flagging_reason = 'ACCOUNT_HACKED'`
3. **DIHE** — `u_metrics.detected_inauthentic_harmful_experience_light_union` where `ato_yn = 1`
4. **SIP Session Kills** — `u_tdsato.sip_killed_members_weekly`
5. **ATO Self Reports** — `u_metrics.gco_case_v2_union` where `ask_path IN ('TS-RHA')` and `category_name IN ('ATO -TnS-', 'Account Compromise - TnS')`

## Additional Tables (from MCP discovery)

| Table | Purpose |
|-------|---------|
| `prod_foundation_tables.fact_ato_mids` | ATO-labeled members with model, source, FP status |
| `pv_aggregate.member_aggregate` | Pageview aggregates (IP, country, UA per member per day) |
| `data_derived.pageviews_member_aggregate_column_daily` | Columnar pageview aggregates (for bcookie joins) |
| `tracking.AntiAbuseJavaScriptDeviceFeaturesDFPWebEvent` | DFP Web — bot score, hosting, routing, proxy, true IP |
| `prod_custservice_column.cs_audit_log_entries` | Columnar CS audit log (for session replay, key events) |
| `prod_auth.two_step_opt_in` | 2FA enrollment status |
| `anti_abuse_device_identification.deviceids` | Device ID linkage across members |
| `data_derived.SecurityLabels_restrictionSnapshot` | Full restriction snapshot (login + spam) |
| `u_fakeacct_copy_from_war.SafireProML_scoresArchived` | Safire fake account scores |
| `tracking.messagesendfunneltrackingevent` | Message send funnel (content analysis, link count) |
| `tracking.PrivateContentScoreEvent` | Message content scoring (spam/URL flags) |
| `u_metrics.ato_volume_union` | ATO volume metrics (for reporting) |
| `u_metrics.detected_inauthentic_harmful_experience_light_union` | DIHE metrics |
| `u_metrics.gco_case_v2_union` | Self-reports (case creation, disposition, status) |
| `tracking.accountmanagementevent` | Close/reactivate events (`action = 'CLOSE_ACCOUNT'` / `'REACTIVATE_ACCOUNT'`) |
| `tracking.logintokenlifecycleevent` | OTP fasttrack detection |
| `u_scaled.cs_audit_ato_log_v1` | Remember me login events |
| `u_far_copy_from_holdem.ghost_lock_login_events` | No-tracking / li-track data for GhostLock cleanup |
| `prod_handlesdb.emailurntostaticemaildatamapping` | Email URN to static email mapping |
| `prod_mlsm.memberauthenticationhistoryv2` | Login history store (100 records, 2yr TTL) |
| `u_tdsfake.segment_self_reports_new_defn_v2` | Self report segmentation |
| `u_metrics.lts_reporting_usage_dimension_pt_union` | Recruiter seat tracking |

## Additional Tracking Events (for ATO Post-Compromise Analysis)

| Table | Purpose |
|-------|---------|
| `tracking.passwordchangeevent` | Password changes (use `memberid`, NOT `header.memberid`) |
| `tracking.memberhandlechangeevent` | Email/phone handle changes |
| `tracking.profileeditevent` | Profile edits (name, photo, headline changes) |
| `tracking.InvitationScoreEvent` | Invitation scoring events |
| `tracking.invitationSaveEvent` | Invitation save events |
| `tracking.userflaggingevent` | User-reported events (account hacked flags) |
| `tracking.scorevent` | Password reset events (`scorertype = 'SCORER_PASSWORD_RESET'`, `scorerstage = 'CURRENT'`) |
| `u_metrics.member_handles_union` | 2FA status check (`has_2fa_enabled`) |

## Related Repos

- `account-takeover-ai-agent-skills` — Full ATO investigation agent with `/investigate-member` and `/reporting-metrics` skills
- `account-integrity-investigation` — IMIR incident response workflows
- `challenges-be` — Backend for security challenges (CAPTCHA, email PIN, phone PIN, IDV, 2FA)
- `trust-account-agents` — Account Abuse Infra agents
- `investigation-agents` — Cipher Crew investigation agents

## DAVI Widgets (run via `davi-runner` skill)

| Widget | Usage | What it does |
|--------|-------|-------------|
| `DiheWidget` | `DiheWidget(account_type="ato", period="7d")` | DIHE breakdown by harm type, product, geography, temporal trend for ATO accounts |
| `IPActivityWidget` | `IPActivityWidget(input_values=[MID1, MID2], period="30d")` | IP/search pivot — find IPs used by suspected ATO MIDs, or MIDs behind suspicious IPs |
| `SevCalculatorWidget` | `SevCalculatorWidget(cohort_member_ids="SELECT mid FROM ...")` | Automated SEV assessment for ATO cohort (DIHE + scraping WoW with charts) |

## Tips

- ATO investigation typically requires `ir2ato` headless account; full member investigation uses `fakeacct`
- Join login events with score events on `submissionid` for full context
- Use `element_at(params, 'memberSessionASN')` to check ASN mismatches
- Device fingerprint fields: `js_df_screenResolution`, `js_df_timezoneOffset`, `js_df_userAgent`, `js_df_colorDepth`
- Key ATO signals: hosting org IPs, UA mismatch, non-standard screen resolution, Linux X11 platforms
- RTT > 199ms in device fingerprinting indicates proxy usage
- VM detection: look for SwiftShader or VMware in `vendorAndRenderer` from WebGL data
- Self-reports table: `u_metrics.dim_gco_case_osc` with `ask_path = 'TS-RHA'` for account compromise
- DFP high-precision rule: `hostingfacility=True` + `ipRoutingType=pop` + `bot_score 600-800` (~23.7% ATO precision)
- `bot_score > 800` with same hosting profile is more likely fake account / scraper than ATO
- CS audit log: `acting_member_id` = who took the action; for CS-initiated actions, use `memberId` for the target
- Safire thresholds: v9_0 > 0.981, v8_2 > 0.995 (for accounts < 30 days old)
- Session replay: same session ID + different browser family + different dates = near-definitive ATO
