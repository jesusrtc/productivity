---
name: payment-events
description: >-
  Reusable SQL query actions for purchase scorer event analysis. Covers payment ID linkage
  across members, member PID density analysis, transaction type breakdowns, country code
  mismatch detection, and payment decline history. Uses tracking.scoreevent with
  scorertype = 'SCORER_PURCHASE' as the primary filter.
allowed-tools: Bash
---

# Payment Events: SQL Query Actions

Reusable Trino SQL query templates for `tracking.scoreevent` filtered to `SCORER_PURCHASE`. Referenced by investigation skills (payment-investigation) instead of duplicating SQL.

**Trino server:** holdem
**Default headless account:** `trustim`
**Partition format:** `YYYY-MM-DD-00`
**Standard filter:** `scorertype = 'SCORER_PURCHASE' AND element_at(params, 'payment_id') IS NOT NULL`

### Presentation Rules (apply when using these queries)

1. **Raw data first, then summaries.** Always present the raw query result rows to the user before any aggregated or summary tables. The user must see the source data before any interpretation.
2. **Evidence-backed assertions only.** Never make a claim without citing the specific data — exact field values, member IDs, and counts from the query results.
3. **RCHARGE requires success/decline context.** Whenever results include RCHARGE counts, always present `declined_recrs_180d` and `successful_recrs_180d` alongside them. High RCHARGE + 0 successful + many declined = abuse signal. High RCHARGE + successful charges = revenue-impacting or legitimate usage. Never show RCHARGE in isolation.
4. **Always check chargeback history.** For every PID under investigation, pull the three chargeback params: `PID_numChargebacksInLast60Days`, `PID_numChargebacksAfterLastNonChargebackResultingTrx`, and `PID_isChargebackProducedBySpecificReasonCode`. Chargebacks are a critical signal for distinguishing abuse from legitimate usage:
   - **DEBIT + 0 chargebacks** = payment was made and not disputed — leans legitimate.
   - **DEBIT + chargebacks > 0** = payment was made and then disputed — strong abuse/stolen card signal.
   - **0 DEBIT + 0 chargebacks + high declined RCHARGE** = charges are being rejected, but the root cause matters. This pattern has multiple explanations:
     - **LinkedIn-side blocking:** If the member is restricted, the `block rcharges for login restricted members` rule intentionally blocks all payment attempts. Check `isLoginRestrictRequired` in the Account Risk Profile — if true, the declines are LinkedIn's defense working as designed, not necessarily a dead/stolen card.
     - **PID blocklisted:** If the PID was auto-blocklisted under PaymentID Reputation based Rules or manually blocked by PAT, declines are expected. Check `PID_PID_Reputation_label`.
     - **Issuer/processor declines:** Insufficient funds, issuer MIT-specific risk controls, or general declines. These are external rejections unrelated to LinkedIn's rules.
     - **Dead/stolen card recycling:** Only conclude this when LinkedIn-side blocking and PID blocklisting are ruled out as causes. The absence of chargebacks here is not exonerating — the card issuer may be declining rather than processing.
   - **`PID_isChargebackProducedBySpecificReasonCode = true`** = chargeback was filed under a fraud-specific reason code (e.g., unauthorized use) — stronger signal than a generic dispute.

---

> **Corporate Card Warning:** Shared payment IDs do not always indicate abuse. Corporate/company cards are legitimately shared across multiple employees (e.g., a marketing team sharing a corporate card for LinkedIn Ads). Corporate cards may show AUTH-only activity as teams stage cards for future legitimate campaigns. When reviewing results, look for corroborating abuse signals (country mismatches, high decline rates, rapid PID cycling) before concluding a PID is malicious. PIDs with only DEBIT/RCHARGE activity across members in the same billing country may be legitimate corporate usage.
>
> **Note on AUTH-only patterns:** AUTH-only activity from non-corporate accounts *may* indicate a staging pattern where abusers are prepping accounts for future waves of purchase abuse (e.g., post-payment ads). However, AUTH-only is also expected in legitimate cases: AUTH is processed as a customer-initiated transaction (CIT) while subsequent Ads charges are merchant-initiated transactions (MIT). A card can pass CIT authorization but fail all MIT attempts due to issuer rules, funds availability, or risk controls specific to merchant-initiated billing. **AUTH success alone is not a sufficient trust signal for card reuse or ongoing payment flows, but AUTH-only is also not sufficient evidence of abuse.** Always require corroborating signals (country mismatches, decline history, PID velocity, PID reputation) before concluding an AUTH-only pattern is malicious.

---

## Queries

### Payment ID Cross-Member Linkage
**When to use:** Identify payment IDs shared across multiple members. Can detect card sharing rings, stolen card reuse, or coordinated abuse where a single payment instrument is used by many accounts. Includes transaction type breakdown, decline/success history, and country code mismatches.
**Important context on PID cross-member reuse:** A PID appearing on multiple members is not automatically suspicious. Whether a PID can be reused depends on why prior charges failed: if the PID was blocklisted (auto or manual by PAT), reuse is blocked everywhere and the linkage is a strong abuse signal. But if prior failures were due to temporary factors (insufficient funds, issuer MIT risk controls, account-level restrictions on the original member), the PID may not be blocklisted, and reuse on another member can occur without abuse. Always check `PID_PID_Reputation_label` and decline context before concluding a cross-member PID is malicious.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD), `{MIN_MEMBERS}` — minimum distinct member count per PID (default: 2)
**Tables:** `tracking.scoreevent`

**Important columns to examine:**
- `auth_count` — number of AUTH (authorization) events for this PID. AUTH events are processed as customer-initiated transactions (CIT). **Important:** multiple AUTH events can appear for the same paymentId (even across different memberIDs) without representing distinct user-initiated card additions — this is expected processor behavior. High auth_count alone does not prove card testing; correlate with other signals (PID density, country mismatches, decline history) before drawing conclusions.
- `rcharge_count` — recurring charge attempts. Recurring Ads charges are processed as merchant-initiated transactions (MIT) and are subject to different issuer risk controls than AUTH/CIT. A card can legitimately pass AUTH but fail all RCHARGE attempts due to issuer MIT-specific rules, funds availability, or account-level restrictions. **Always interpret alongside `declined_recrs_180d` and `successful_recrs_180d`** — never present RCHARGE in isolation. Additionally, check whether declines are caused by LinkedIn's own rules (see `isLoginRestrictRequired` and `PID_PID_Reputation_label` in the Account Risk Profile query) vs. external issuer/processor rejections — these have very different implications.
- `declined_recrs_180d` — is this PID getting high volumes of declines? Must always be shown with RCHARGE data.
- `successful_recrs_180d` — is this PID allowing recurring transactions to actually be approved? Must always be shown with RCHARGE data.
- `chargebacks_60d` — number of chargebacks filed against this PID in the last 60 days. Non-zero after a DEBIT = stolen card / unauthorized use.
- `chargebacks_after_last_trx` — chargebacks filed after the most recent non-chargeback transaction. Indicates the card holder disputed a recent charge.
- `chargeback_specific_reason` — whether the chargeback was filed under a fraud-specific reason code (e.g., unauthorized use). `true` is a stronger abuse signal than a generic dispute.
- `ip_vs_billing_mismatches` — how often does the IP address differ from the billing country code?
- `ip_vs_bank_mismatches` — how often does the IP differ from the bank country code?
- `billing_vs_bank_mismatches` — how often do the billing and bank country codes mismatch?

```sql
SELECT
  element_at(params, 'payment_id') AS pid,
  COUNT(DISTINCT header.memberid) AS number_of_mids,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT CAST(header.memberid AS VARCHAR)), ', ') AS mids_connected,
  CASE
    WHEN COUNT(DISTINCT header.memberid) >= 4 THEN 'High MID linkage (PID used by 4+ MIDs)'
    WHEN COUNT(DISTINCT header.memberid) BETWEEN 2 AND 3 THEN 'Moderate MID linkage (PID used by 2-3 MIDs)'
    ELSE 'Normal (single MID)'
  END AS payment_signal,
  COUNT(*) AS total_transactions,
  SUM(CASE WHEN element_at(params, 'transactionType') = 'AUTH' THEN 1 ELSE 0 END) AS auth_count,
  SUM(CASE WHEN element_at(params, 'transactionType') = 'PREAUTH' THEN 1 ELSE 0 END) AS preauth_count,
  SUM(CASE WHEN element_at(params, 'transactionType') = 'DEBIT' THEN 1 ELSE 0 END) AS debit_count,
  SUM(CASE WHEN element_at(params, 'transactionType') = 'RCHARGE' THEN 1 ELSE 0 END) AS rcharge_count,
  MAX(element_at(params, 'PID_numDeclinedRecrsInLast180Days')) AS declined_recrs_180d,
  MAX(element_at(params, 'PID_numSuccessfulRecrsInLast180Days')) AS successful_recrs_180d,
  MAX(element_at(params, 'PID_numChargebacksInLast60Days')) AS chargebacks_60d,
  MAX(element_at(params, 'PID_numChargebacksAfterLastNonChargebackResultingTrx')) AS chargebacks_after_last_trx,
  MAX(element_at(params, 'PID_isChargebackProducedBySpecificReasonCode')) AS chargeback_specific_reason,
  SUM(CASE WHEN element_at(params, 'geo.cc') IS NOT NULL
    AND element_at(params, 'billingCountryCode') IS NOT NULL
    AND UPPER(element_at(params, 'geo.cc')) != UPPER(element_at(params, 'billingCountryCode'))
    THEN 1 ELSE 0 END) AS ip_vs_billing_mismatches,
  SUM(CASE WHEN element_at(params, 'geo.cc') IS NOT NULL
    AND element_at(params, 'bankCountryCode') IS NOT NULL
    AND UPPER(element_at(params, 'geo.cc')) != UPPER(element_at(params, 'bankCountryCode'))
    THEN 1 ELSE 0 END) AS ip_vs_bank_mismatches,
  SUM(CASE WHEN element_at(params, 'billingCountryCode') IS NOT NULL
    AND element_at(params, 'bankCountryCode') IS NOT NULL
    AND UPPER(element_at(params, 'billingCountryCode')) != UPPER(element_at(params, 'bankCountryCode'))
    THEN 1 ELSE 0 END) AS billing_vs_bank_mismatches,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(params, 'billingCountryCode')), ', ') AS billing_countries,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(params, 'bankCountryCode')), ', ') AS bank_countries,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(params, 'geo.cc')), ', ') AS geo_ip_countries
FROM hive.tracking.scoreevent
WHERE datepartition >= '{START_DATE}-00'
  AND datepartition <= '{END_DATE}-00'
  AND scorertype = 'SCORER_PURCHASE'
  AND element_at(params, 'payment_id') IS NOT NULL
GROUP BY element_at(params, 'payment_id')
HAVING COUNT(DISTINCT header.memberid) >= {MIN_MEMBERS}
ORDER BY number_of_mids DESC
```

---

### Member Payment ID Density
**When to use:** Identify members with unusually high numbers of payment IDs linked to their account. Detects card testing, stolen card cycling, or fraud rings where a single member is burning through payment instruments. Includes transaction type breakdown, country code mismatches, and account age to distinguish newly created staging accounts from established members.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD), `{MIN_PIDS}` — minimum distinct PID count per member (default: 2)
**Tables:** `tracking.scoreevent`, `prod_foundation_tables.dim_member_all`

**Signal thresholds:**
- 6+ PIDs linked → High PID density (strong fraud signal)
- 3-5 PIDs linked → Elevated PID density (warrants investigation)
- 2 PIDs linked → Low PID density (may be benign, check context)

**Account age context:**

> **False positive warning:** A new account with 1-2 AUTH PIDs alone is NOT sufficient to conclude abuse. New users legitimately add payment methods when signing up for LinkedIn Ads or Premium. Only escalate new accounts when AUTH-only activity is combined with **at least one** corroborating signal: high PID density (3+), country code mismatches, PIDs shared with other flagged members, `PID_fake_accounts > 0`, `accountLabel = FAKE`, elevated decline history, or 0 connections with `spamRestrictRequired = true`. The more signals that converge, the higher the confidence.

- Very New (0-7 days) + AUTH-only + **corroborating signals** → likely staging for abuse
- Very New (0-7 days) + AUTH-only + no other signals → **likely legitimate new user, do not flag**
- New (8-30 days) + AUTH-only + corroborating signals → strong abuse signal
- Established (90+ days) + AUTH-only + IP mismatches → possible account compromise, investigate further

```sql
SELECT
  CAST(se.header.memberid AS VARCHAR) AS mid,
  FROM_UNIXTIME(m.registration_date_ts / 1000) AS registration_date,
  DATE_DIFF('day', CAST(FROM_UNIXTIME(m.registration_date_ts / 1000) AS DATE), CURRENT_DATE) AS account_age_days,
  CASE
    WHEN DATE_DIFF('day', CAST(FROM_UNIXTIME(m.registration_date_ts / 1000) AS DATE), CURRENT_DATE) <= 7 THEN 'Very New (0-7 days)'
    WHEN DATE_DIFF('day', CAST(FROM_UNIXTIME(m.registration_date_ts / 1000) AS DATE), CURRENT_DATE) <= 30 THEN 'New (8-30 days)'
    WHEN DATE_DIFF('day', CAST(FROM_UNIXTIME(m.registration_date_ts / 1000) AS DATE), CURRENT_DATE) <= 90 THEN 'Recent (31-90 days)'
    ELSE 'Established (90+ days)'
  END AS account_age_bucket,
  COUNT(DISTINCT element_at(se.params, 'payment_id')) AS number_of_pids,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'payment_id')), ', ') AS pids_connected,
  CASE
    WHEN COUNT(DISTINCT element_at(se.params, 'payment_id')) >= 6 THEN 'High PID density (6+ PIDs linked)'
    WHEN COUNT(DISTINCT element_at(se.params, 'payment_id')) BETWEEN 3 AND 5 THEN 'Elevated PID density (3-5 PIDs linked)'
    WHEN COUNT(DISTINCT element_at(se.params, 'payment_id')) = 2 THEN 'Low PID density (2 PIDs linked)'
    ELSE 'Normal (single PID)'
  END AS payment_signal,
  COUNT(*) AS total_transactions,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'AUTH' THEN 1 ELSE 0 END) AS auth_count,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'PREAUTH' THEN 1 ELSE 0 END) AS preauth_count,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'DEBIT' THEN 1 ELSE 0 END) AS debit_count,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'RCHARGE' THEN 1 ELSE 0 END) AS rcharge_count,
  SUM(CASE WHEN element_at(se.params, 'geo.cc') IS NOT NULL
    AND element_at(se.params, 'billingCountryCode') IS NOT NULL
    AND UPPER(element_at(se.params, 'geo.cc')) != UPPER(element_at(se.params, 'billingCountryCode'))
    THEN 1 ELSE 0 END) AS ip_vs_billing_mismatches,
  SUM(CASE WHEN element_at(se.params, 'geo.cc') IS NOT NULL
    AND element_at(se.params, 'bankCountryCode') IS NOT NULL
    AND UPPER(element_at(se.params, 'geo.cc')) != UPPER(element_at(se.params, 'bankCountryCode'))
    THEN 1 ELSE 0 END) AS ip_vs_bank_mismatches,
  SUM(CASE WHEN element_at(se.params, 'billingCountryCode') IS NOT NULL
    AND element_at(se.params, 'bankCountryCode') IS NOT NULL
    AND UPPER(element_at(se.params, 'billingCountryCode')) != UPPER(element_at(se.params, 'bankCountryCode'))
    THEN 1 ELSE 0 END) AS billing_vs_bank_mismatches,
  MAX(element_at(se.params, 'PID_numChargebacksInLast60Days')) AS chargebacks_60d,
  MAX(element_at(se.params, 'PID_numChargebacksAfterLastNonChargebackResultingTrx')) AS chargebacks_after_last_trx,
  MAX(element_at(se.params, 'PID_isChargebackProducedBySpecificReasonCode')) AS chargeback_specific_reason,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'billingCountryCode')), ', ') AS billing_countries,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'bankCountryCode')), ', ') AS bank_countries,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'geo.cc')), ', ') AS geo_ip_countries
FROM hive.tracking.scoreevent se
JOIN hive.prod_foundation_tables.dim_member_all m
  ON se.header.memberid = m.member_id
WHERE se.datepartition >= '{START_DATE}-00'
  AND se.datepartition <= '{END_DATE}-00'
  AND se.scorertype = 'SCORER_PURCHASE'
  AND element_at(se.params, 'payment_id') IS NOT NULL
GROUP BY se.header.memberid, m.registration_date_ts
HAVING COUNT(DISTINCT element_at(se.params, 'payment_id')) >= {MIN_PIDS}
ORDER BY number_of_pids DESC
```

---

### Member Account Risk Profile
**When to use:** Enrich members identified from PID density or cross-member linkage queries with account reputation, ATO/fake account flags, and payment reputation signals. Use to determine whether flagged members are fake accounts, compromised accounts, or legitimate users.
**Parameters:** `{START_DATE}`, `{END_DATE}` — date range (YYYY-MM-DD), `{MEMBER_IDS}` — comma-separated list of member IDs to investigate (e.g., `1048406847, 770985613, 814751013`)
**Tables:** `tracking.scoreevent`, `prod_foundation_tables.dim_member_all`, `prod_foundation_tables.dim_member_trust_restrictions`

**Key signals to interpret:**
- `scoring_result` — the purchase scorer's actual decision: `PROVISION` (allowed), `CHALLENGE`, or `REJECT`. This is the most direct signal for whether LinkedIn's defenses acted on this transaction.
- `activated_rules` — which payment rules fired (e.g., `block rcharges for login restricted members`, `PaymentID Reputation based Rules`). `null` means no rules triggered. When investigating RCHARGE declines, this field distinguishes LinkedIn-side blocking from issuer/processor declines.
- `dfp_risk_score` — Device Fingerprinting risk score (numeric, lower = less risky). Scores under ~20 are generally low risk. Higher scores indicate device-level risk signals (VPN, proxy, emulator, etc.).
- `dfp_reason_codes` — why DFP flagged the transaction (e.g., `DEVICE_IP_ADDRESS`, `PAYMENT_INSTRUMENT_RISK_LEVEL`). Useful for understanding what triggered DFP concern.
- `dfp_merchant_rule_decision` — DFP's own rule decision (`Approve`/`Review`/`Decline`). Independent from LinkedIn's scorer decision.
- `auth_processor_result` — the payment processor's response to AUTH attempts. Empty string = no explicit rejection. Non-empty values indicate processor-level failures.
- `PID_fake_accounts` / `PID_fake_account_restriction_ratio` — how many fake accounts are already associated with this member's PIDs? High ratio = PID is circulating in a known abuse ring.
- `PID_historical_atos` — are there known account takeovers linked to this PID? Non-zero = compromised card or ATO chain.
- `PID_is_corporate_card` — if `true`, deprioritize this member (likely legitimate shared corporate card).
- `internal_member_reputation_label` / `profile_memberReputationLabel` — the system's current assessment of this member.
- `accountLabel` — account classification (e.g., normal, suspicious).
- `profile_accountAgeInDays` — account age as reported by the scorer (cross-check with `dim_member_all`).
- `registrationScore` — the score assigned at registration. Low scores on new accounts = slipped past defenses.
- `isLoginRestrictRequired` / `isSpamRestrictRequired` — whether existing rules flagged this member for restriction.
- `profile_isSpamRestricted` — whether the account is already spam-restricted.
- `is_currently_restricted` — whether the account has an active trust restriction.
- `restriction_reasons` — why the account was restricted (if applicable).

**Pattern interpretation:**
- New account + high PID density (3+) + `PID_fake_accounts > 0` + not restricted → **fake account slipping through defenses**
- New account + 1-2 PIDs + no IP mismatches + no PID reputation flags + no `accountLabel = FAKE` → **likely legitimate new user, do not flag** (new users adding a payment method is normal onboarding)
- Established account + `PID_historical_atos > 0` + `isLoginRestrictRequired = true` → **likely ATO, card compromised**
- `PID_is_corporate_card = true` + no restriction flags + consistent geo → **likely legitimate, deprioritize**
- High `PID_fake_account_restriction_ratio` + `profile_isSpamRestricted = false` → **known bad PID, member not yet actioned**
- `scoring_result = REJECT` + `activated_rules` contains rule name → **LinkedIn actively blocking this member's payments** — the decline is intentional, not an issuer issue
- `scoring_result = PROVISION` + all RCHARGEs declined + no activated rules → **declines are issuer/processor-side**, not LinkedIn. Check `auth_processor_result` and geo mismatches for root cause.
- `dfp_risk_score` high (40+) + `dfp_merchant_rule_decision = Review/Decline` → **device-level risk** — possible VPN, proxy, emulator, or compromised device
- `dfp_risk_score` low (<20) + `dfp_merchant_rule_decision = Approve` → **device appears clean**, deprioritize device as an abuse vector
- **Single-signal members should not be flagged as abusive.** Require at least 2 converging signals before classifying a member as suspicious.

```sql
SELECT
  CAST(se.header.memberid AS VARCHAR) AS mid,
  FROM_UNIXTIME(m.registration_date_ts / 1000) AS registration_date,
  DATE_DIFF('day', CAST(FROM_UNIXTIME(m.registration_date_ts / 1000) AS DATE), CURRENT_DATE) AS account_age_days,
  m.is_restricted,
  r.restriction_reasons,
  r.restriction_date,
  -- Scoring decision and activated rules
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'result')), ', ') AS scoring_results,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'activatedrules')), ' | ') AS activated_rules,
  -- DFP signals
  MAX(element_at(se.params, 'dfpRiskScore')) AS dfp_risk_score,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'dfpReasonCodes')), ' | ') AS dfp_reason_codes,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT element_at(se.params, 'dfpMerchantRuleDecision')), ', ') AS dfp_merchant_rule_decision,
  MAX(element_at(se.params, 'authProcessorResult')) AS auth_processor_result,
  -- Account profile
  MAX(element_at(se.params, 'profile_accountAgeInDays')) AS profile_account_age_days,
  MAX(element_at(se.params, 'profile_connectionCount')) AS connection_count,
  MAX(element_at(se.params, 'accountLabel')) AS account_label,
  MAX(element_at(se.params, 'internal_member_reputation_label')) AS member_reputation,
  MAX(element_at(se.params, 'profile_memberReputationLabel')) AS profile_reputation_label,
  MAX(element_at(se.params, 'registrationScore')) AS registration_score,
  MAX(element_at(se.params, 'email_state')) AS email_state,
  MAX(element_at(se.params, 'isLoginRestrictRequired')) AS login_restrict_required,
  MAX(element_at(se.params, 'isSpamRestrictRequired')) AS spam_restrict_required,
  MAX(element_at(se.params, 'profile_isSpamRestricted')) AS is_spam_restricted,
  MAX(element_at(se.params, 'profile_isRestrictionWhitelisted')) AS is_restriction_whitelisted,
  -- PID reputation
  MAX(element_at(se.params, 'PID_PID_Reputation_label')) AS pid_reputation_label,
  MAX(element_at(se.params, 'PID_fake_accounts')) AS pid_fake_accounts,
  MAX(element_at(se.params, 'PID_fake_account_restriction_ratio')) AS pid_fa_restriction_ratio,
  MAX(element_at(se.params, 'PID_fake_accounts_payment_fraud_reason')) AS pid_fa_fraud_reason,
  MAX(element_at(se.params, 'PID_historical_atos')) AS pid_historical_atos,
  MAX(element_at(se.params, 'PID_is_corporate_card')) AS pid_is_corporate_card,
  MAX(element_at(se.params, 'PID_overall_members')) AS pid_overall_members,
  MAX(element_at(se.params, 'PID_restrictions_overturned')) AS pid_restrictions_overturned,
  MAX(element_at(se.params, 'PID_numDeclinedRecrsInLast180Days')) AS declined_recrs_180d,
  MAX(element_at(se.params, 'PID_numSuccessfulRecrsInLast180Days')) AS successful_recrs_180d,
  MAX(element_at(se.params, 'PID_numChargebacksInLast60Days')) AS chargebacks_60d,
  MAX(element_at(se.params, 'PID_numChargebacksAfterLastNonChargebackResultingTrx')) AS chargebacks_after_last_trx,
  MAX(element_at(se.params, 'PID_isChargebackProducedBySpecificReasonCode')) AS chargeback_specific_reason,
  -- Transaction summary
  COUNT(DISTINCT element_at(se.params, 'payment_id')) AS number_of_pids,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'AUTH' THEN 1 ELSE 0 END) AS auth_count,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'DEBIT' THEN 1 ELSE 0 END) AS debit_count,
  SUM(CASE WHEN element_at(se.params, 'transactionType') = 'RCHARGE' THEN 1 ELSE 0 END) AS rcharge_count,
  SUM(CASE WHEN UPPER(element_at(se.params, 'geo.cc')) != UPPER(element_at(se.params, 'billingCountryCode'))
    THEN 1 ELSE 0 END) AS ip_vs_billing_mismatches,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT UPPER(element_at(se.params, 'geo.cc'))), ', ') AS geo_ip_countries,
  ARRAY_JOIN(ARRAY_AGG(DISTINCT UPPER(element_at(se.params, 'billingCountryCode'))), ', ') AS billing_countries
FROM hive.tracking.scoreevent se
JOIN hive.prod_foundation_tables.dim_member_all m
  ON se.header.memberid = m.member_id
LEFT JOIN hive.prod_foundation_tables.dim_member_trust_restrictions r
  ON se.header.memberid = r.member_id
  AND r.is_current = true
WHERE se.datepartition >= '{START_DATE}-00'
  AND se.datepartition <= '{END_DATE}-00'
  AND se.scorertype = 'SCORER_PURCHASE'
  AND element_at(se.params, 'payment_id') IS NOT NULL
  AND se.header.memberid IN ({MEMBER_IDS})
GROUP BY se.header.memberid, m.registration_date_ts, m.is_restricted,
         r.restriction_reasons, r.restriction_date
ORDER BY account_age_days ASC
```
