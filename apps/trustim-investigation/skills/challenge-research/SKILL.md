---
name: challenge-research
description: >-
  Investigate security challenge effectiveness using Trino queries. Covers captcha, phone,
  email pin, SSP/SHC, IDV challenges, and challenge bypass patterns.
  Use when analyzing challenge solve rates or challenge evasion.
allowed-tools: Bash
---

# Challenge Research

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

**Partition format:** `YYYY-MM-DD-00`

## Key Tables

| Table | Purpose |
|-------|---------|
| `tracking.securitychallengeevent` | Challenge events (type, result, validation) |
| `tracking_column.securitychallengeevent` | Columnar challenge events |
| `tracking.scoreevent` | Score events with challenge decisions |
| `tracking.phonescoreevent` | Phone verification scoring with telesign |

## Investigation Queries

The SQL for all queries below lives in the **`challenge-events`** action skill. Invoke that skill and use the named query listed for each step.

### 1. Challenge Volume by Type
**Action:** `challenge-events` → *Challenge Volume by Type*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use as the first query when investigating any challenge anomaly

### 2. Captcha Challenge Solve Rate
**Action:** `challenge-events` → *Captcha Challenge Solve Rate*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to track daily captcha effectiveness; drop in solve rate = evasion

### 3. JavaScript Challenge Analysis
**Action:** `challenge-events` → *JavaScript Challenge Analysis*
- Params: `{START_DATE}` — start of the date range
- Use to monitor JS challenge pass-through rate over time

### 4. Phone Challenge with Telesign Risk Score
**Action:** `challenge-events` → *Phone Challenge with Telesign Risk Score*
- Params: `{START_DATE}` — start of the date range
- Use to analyze carrier and risk distributions in phone challenges

### 5. Email Pin Challenge Flow
**Action:** `challenge-events` → *Email Pin Challenge Flow*
- Params: `{START_DATE}`, `{END_DATE}` — the date range
- Use to track members challenged and solved rate for email pin

### 6. SSP/SHC Challenge Eligibility After Email Pin
**Action:** `challenge-events` → *SSP/SHC Challenge Eligibility After Email Pin*
- Params: `{DATE}` — the target date
- Use to tune SSP eligibility thresholds after email pin resolution

### 7. IDV (Identity Verification) Metrics
**Action:** `challenge-events` → *IDV Metrics*
- Params: `{START_DATE}` — start of the date range; `{IDV_METRICS_TABLE}` — confirm table name with DESCRIBE
- Use to track IDV funnel (shown → uploaded → approved)

### 8. Email Bounce Detection (Fake Signup Signal)
**Action:** `challenge-events` → *Email Bounce Detection*
- Params: `{START_DATE}` — start of the date range
- Use to identify registrations with invalid email addresses (hard bounce = classification 10)

### 9. Arkose Suspicious Activity Detection
**Action:** `challenge-events` → *Arkose Suspicious Activity Detection*
- Params: `{START_DATE}` — start of the date range
- Use to track Arkose bot detection volume over time

### 10. IDV Appeal Verification
**Action:** `challenge-events` → *IDV Appeal Verification*
- Params: `{START_DATE}` — start of the date range; update `{SCHEMA}` to the headless schema with the appeal MID table
- Use to track IDV outcomes for members in the appeal flow

## Tips

- Challenge types: `CAPTCHA`, `JAVASCRIPT_CHALLENGE`, `EMAIL_PIN`, `SMS`, `PHONE_CHALLENGE`, `COUNTRY_VALIDATION`, `SELFIE_VERIFICATION`
- `eventtype`: `SHOW_CHALLENGE`, `SUBMIT_CHALLENGE`
- `validationresult`: `USER_RESPONSE_CORRECT`, `USER_RESPONSE_INCORRECT`, `TIMED_OUT`
- Phone scoring: telesignscoreresponse array index 17=carrier, 18=risk_score
- Shape-detected bot signal: `element_at(params, 'isShapeDetectedBot') = 'true'`
- Email bounce classifications: 10=hard bounce (invalid mailbox), 1=undetermined, 40=generic bounce
- Arkose: `tracking.ArkoseLabsRealTimeLoggingEvent` for bot detection vendor data
- IDV document types: `DRIVING_LICENSE`, `ID_CARD`, `PASSPORT`, `PAN_CARD`, `RESIDENCE_PERMIT`
- Vendor bot detection: `tracking.VendorBotDetectionEvent` for Shape/Human Security signals

## Challenges Backend Architecture (from MCP: challenges-be)

The `challenges-be` service provides APIs to create, manage, and verify security challenges. Key components:
- **ChallengeInstanceResource** — Main Rest.li endpoint for CRUD on challenge instances
- **ChallengeInstanceCreatorManager** — Factory for challenge-type-specific creation
- **ChallengeCache** — Couchbase-based caching for time-sensitive challenge data
- Backed by Espresso database for persistence

Challenge types served: CAPTCHA, Email PIN, Phone PIN, ID Verification, 2FA, Evercaptcha, Fun Captcha, Rehab Restriction, Secondary Handle, SMS, Country Validation

## VoIP Phone Abuse

VoIP phone numbers are a primary vector for bypassing phone-based security challenges at scale.

### Detection
- Table: `TRACKING_hourly.MemberAccountManagementScoreEvent`
- Key fields: `telesignscoreresponse.riskscore`, `.phonetype`, `.carrier`, `.countryiso2`
- Filter: `phonetype = 'VOIP' AND carrier NOT LIKE 'Google%'` OR `riskscore > 900`
- 99.8% recall, 92%+ precision

### Top Abusive Carriers
| Carrier | Accounts | Share |
|---------|----------|-------|
| ISP Telecom - ISP Telecom - SVR | 369 | ~63% of abuse |
| Number Access | 210 | ~29% of abuse |

These two carriers account for ~92% of VoIP phone abuse.

### Reference
- [VoIP 2FA investigation](https://docs.google.com/document/d/1CHToDsE_ZYNyfviXwd93Muu_v-m_sGbQtFYy8Y8PKeg/edit)

## IRSF (International Revenue Share Fraud)

IRSF exploits SMS delivery to premium-rate phone numbers for revenue generation, without any intent to complete the challenge.

### Pattern
FA created → phone added → account restricted → PWR initiated → SMS still sent to restricted accounts (bug in legacy logic)

### Detection
- 0% completion rate on SMS-triggered flows = IRSF indicator (vs normal FA abuse which completes some flows)
- Mauritius spike: ~7.5K accounts generating multiple SMS/day, ~$38K/month cost

### Root Cause
Legacy logic blocked `SECONDARY_HANDLE_CHALLENGE` and `LIVENESS_CHECK` for restricted accounts but did NOT block SMS delivery on PWR flows.

### Fix
- PR: `kryptonite-prelogin-integrity/pull/1386`

### References
- [IRSF investigation #1](https://docs.google.com/document/d/14KSwNx0M6GqcyANUUUpod2OvQgcBRa4_Oxh6OG0Q-JQ/edit)
- [IRSF investigation #2](https://docs.google.com/document/d/1fHEe_lpiS5LJylyFrbNkUl9R_2BiRMhaDd3JNlRJrBI/edit)

## SMS Cost Awareness

When investigating SMS-related abuse, consider the cost impact by geography.

### High-Cost Geos (>$0.20/transaction)
Bhutan, Tajikistan, Madagascar, Uzbekistan, Syria, Sri Lanka, Azerbaijan, Togo, Burundi, Ethiopia

- Average global SMS cost: ~$0.10/transaction
- IRSF and VoIP abuse targeting high-cost geos can cause disproportionate financial impact

### Reference
- [SMS cost-reduction analysis](https://docs.google.com/document/d/13fC2-JOF2rYDbdG8eIgNYz6-GWrl2Jmnwi7OXPXBdGE/edit)

## Related Repos
- `challenges-be` — Backend service for all challenge types
- `account-experience-docs` — Oncall docs for challenge debugging (in `docs/oncall-docs/issue-triage/challenges/`)
