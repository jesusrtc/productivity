---
name: telesign-triage
description: >-
  Triage Telesign SMS incidents: vendor blocked errors, dynamic threshold changes,
  risk score shifts, retry amplification, and cost impact analysis.
  Use when oncall for SMS delivery failures, VENDOR_BLOCKED_ERROR spikes,
  or Telesign threshold escalations.
allowed-tools: Bash
---

# Telesign Triage

## How Telesign SMS Works at LinkedIn

LinkedIn sends SMS through Telesign for: 2FA login verification, registration phone verification, password reset, account settings phone changes. Telesign assigns a dynamic risk score to each phone number per country. When the score exceeds their threshold, SMS is dropped with `VENDOR_BLOCKED_ERROR`. Telesign adjusts thresholds dynamically based on volume patterns they observe; they can raise thresholds without notifying us first.

## How to Use This Skill

**Queries below are REFERENCE TEMPLATES only.** For actual investigations:
1. Run `DESCRIBE {table_name}` to check current schema before constructing queries
2. Build queries based on the live schema -- columns may have changed
3. Always use GROUP BY / COUNT / COUNT(DISTINCT) to aggregate results and minimize token usage
4. Always filter on `datepartition` and use `LIMIT`
5. Never return raw PII -- aggregate by country, carrier, source, etc. instead of individual values
6. For missing investigative context, use Captain MCP tools (`unified_context_search`, `search_confluence_content`, `read_google_docs_document`) or ask the user
Use the Captain MCP `execute_trino_query` tool on **holdem** server.

## Key Tables

| Table | Headless | Purpose |
|-------|----------|---------|
| `u_tdsfraud.telesign_sec_show_challange_retina` | `tdsfraud` | Pre-aggregated daily Telesign data by source, country, challenge type. **Start here for any triage.** |
| `tracking.phonescoreevent` | `trustim` | Raw phone scoring events with full Telesign response (risk score, carrier, phone type) |
| `tracking.messagedroppedevent` | `trustim` | SMS that Telesign refused to deliver. Use dot-notation table. |
| `tracking.messagedeliveryevent` | `trustim` | Successfully delivered SMS |
| `u_tdsfraud.telesign_phone_score_cost` | `tdsfraud` | Cost analysis |
| `u_tdsfraud.telesign_sms_pricing_table` | `tdsfraud` | SMS pricing by country |

## Country Code Formats

| Table | Column | Format | Example |
|-------|--------|--------|---------|
| `messagedroppedevent` | `locale.country` | 2-letter uppercase | `IT` |
| `messagedeliveryevent` | `locale.country` | 2-letter uppercase | `IT` |
| `telesign_sec_show_challange_retina` | `ip_cntry` | 3-letter lowercase | `ita` |
| `phonescoreevent` | `telesignscoreresponse.countryiso2` | 2-letter uppercase | `IT` |
| `phonescoreevent` | `ip_country(ip2str(...))` | 3-letter lowercase | `ita` |

## Triage Flow

### Step 1: Identify What Is Being Blocked

Check dropped SMS by country and campaign to scope the incident.

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT datepartition, campaignname,
  COUNT(*) AS drops,
  COUNT(DISTINCT header.memberid) AS unique_members
FROM tracking.messagedroppedevent
WHERE exceptioninfo.exceptiontype = 'VENDOR_BLOCKED_ERROR'
  AND smsdroppedinfo.smsmessagetype IS NOT NULL
  AND locale.country = '{COUNTRY_2LETTER}'
  AND datepartition >= concat('{START}', '-00')
  AND datepartition <= concat('{END}', '-00')
GROUP BY 1, 2
ORDER BY 1 ASC, drops DESC
```

Key campaign values:
- `sms_security_two_step_verification_pin` -- 2FA login
- `sms_security_add_email_notification` -- email add notification

### Step 2: Identify the Source Driving Telesign Volume

This is the most important query. It shows which flow is generating the SMS volume that Telesign sees.

```sql
SET SESSION li_authorization_user = 'tdsfraud';

SELECT datepartition, source,
  SUM(num_distinct_message) AS messages
FROM u_tdsfraud.telesign_sec_show_challange_retina
WHERE ip_cntry = '{COUNTRY_3LETTER}'
  AND datepartition >= concat('{START}', '-00')
  AND datepartition <= concat('{END}', '-00')
GROUP BY 1, 2
ORDER BY 1 ASC, messages DESC
```

Source values:
- `REGISTER_WITH_EMAIL` -- registration phone verification (most common abuse source)
- `CONSUMER_LOGIN` -- 2FA login verification
- `PASSWORD_RESET` -- password reset phone verification
- `SETTINGS_ADD_PHONE` -- member adding phone in settings
- `REGISTER_WITH_PHONE_NUMBER` -- registration with phone
- `SETTINGS_CHANGE` -- member changing phone in settings

### Step 3: Check Telesign Risk Score Distribution

Shows whether Telesign raised risk scores for the entire country or correctly isolated abuse as HIGH.

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT datepartition, telesignscoreresponse.risklevel,
  COUNT(*) AS total
FROM tracking.phonescoreevent
WHERE telesignscoreresponse.countryiso2 = '{COUNTRY_2LETTER}'
  AND scorerstage = 'CURRENT'
  AND datepartition >= concat('{START}', '-00')
  AND datepartition <= concat('{END}', '-00')
GROUP BY 1, 2
ORDER BY 1 ASC, total DESC
```

What to look for:
- **HIGH spikes with stable MEDIUM_LOW** = abuse correctly isolated (no action needed)
- **MEDIUM_LOW collapse** = Telesign raised scores across the board (collateral damage, escalate)

### Step 4: Determine If Abuse Is Still Active

Check if the spike source has returned to baseline. For registration abuse, look at guest traffic (memberid=0).

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT datepartition,
  CASE WHEN header.memberid = 0 THEN 'guest' ELSE 'member' END AS user_type,
  CASE WHEN registrationscore IS NOT NULL THEN 'registration' ELSE 'other' END AS flow,
  COUNT(*) AS total
FROM tracking.phonescoreevent
WHERE telesignscoreresponse.countryiso2 = '{COUNTRY_2LETTER}'
  AND scorerstage = 'CURRENT'
  AND datepartition >= concat('{START}', '-00')
  AND datepartition <= concat('{END}', '-00')
GROUP BY 1, 2, 3
ORDER BY 1 ASC, total DESC
```

### Step 5: Check for Retry Amplification

Combine delivered + dropped to see total SMS demand vs baseline.

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT datepartition,
  COUNT_IF(event_type = 'delivered') AS delivered,
  COUNT_IF(event_type = 'dropped') AS dropped,
  COUNT(*) AS total
FROM (
  SELECT datepartition, 'delivered' AS event_type
  FROM tracking.messagedeliveryevent
  WHERE messagetype = 'SMS'
    AND locale.country = '{COUNTRY_2LETTER}'
    AND datepartition >= concat('{START}', '-00')
    AND datepartition <= concat('{END}', '-00')
  UNION ALL
  SELECT datepartition, 'dropped' AS event_type
  FROM tracking.messagedroppedevent
  WHERE exceptioninfo.exceptiontype = 'VENDOR_BLOCKED_ERROR'
    AND smsdroppedinfo.smsmessagetype IS NOT NULL
    AND locale.country = '{COUNTRY_2LETTER}'
    AND datepartition >= concat('{START}', '-00')
    AND datepartition <= concat('{END}', '-00')
) combined
GROUP BY 1
ORDER BY 1 ASC
```

If total > baseline but login volume is flat, the excess is retries from blocked members, not new abuse.

### Step 6: Profile Impacted Members

Pull top dropped MIDs and verify they are legitimate.

```sql
-- Top dropped members
SET SESSION li_authorization_user = 'trustim';

SELECT header.memberid AS mid, COUNT(*) AS drops
FROM tracking.messagedroppedevent
WHERE exceptioninfo.exceptiontype = 'VENDOR_BLOCKED_ERROR'
  AND locale.country = '{COUNTRY_2LETTER}'
  AND campaignname = 'sms_security_two_step_verification_pin'
  AND datepartition >= concat('{START}', '-00')
  AND datepartition <= concat('{END}', '-00')
GROUP BY 1
ORDER BY drops DESC
LIMIT 20
```

Then check against `prod_foundation_tables.dim_member_all` for `member_id`, `country_code`, `is_restricted`, `restriction_type`, `number_of_positions`, `number_of_educations`, `connection_count_bucket`, `registration_date_ts`, `last_login_time`.

### Step 7: Check LinkedIn-Side Phone Scorer Rules

See what LinkedIn's phone scorer is accepting vs rejecting before traffic reaches Telesign.

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT array_join(activatedlogic.droolsrules, ',') AS rules,
  COUNT(*) AS total
FROM tracking.phonescoreevent
WHERE telesignscoreresponse.countryiso2 = '{COUNTRY_2LETTER}'
  AND scorerstage = 'CURRENT'
  AND datepartition = concat('{DATE}', '-00')
GROUP BY 1
ORDER BY total DESC
LIMIT 10
```

Key drools rules:
- `deny for using phone number too many times - email reg` -- rate limiting on registration
- `block denylisted numbers` -- blacklisted phone numbers
- `deny previously used numbers` -- phone already used on another account
- `deny for using phone number more than once with bad IP` -- IP reputation + phone reuse
- `default accept` -- no rule triggered, traffic passes through to Telesign

If `default accept` dominates during an abuse spike, the rate limiting needs tightening.

## Key Patterns

### Retry Amplification Loop
Telesign blocks SMS, members retry, inflated volume sustains elevated risk scoring. Signature: total SMS volume increasing while unique login volume is flat. Each blocked member generates ~3-4 retries.

### Registration Abuse Triggering Country-Wide Blocks
Guest registration phone verification (`REGISTER_WITH_EMAIL`, `memberid=0`) spikes volume for a country. Telesign raises dynamic threshold for the whole country, collaterally blocking 2FA for legitimate members. Ref: Italy April 2026 (REGISTER_WITH_EMAIL peaked at 18.9K/day, Telesign raised Italy threshold to 601, blocked 83% of 2FA members).

### VoIP/IRSF Abuse
Check `telesignscoreresponse.phonetype = 'VOIP'` and carrier. Top abusive carriers historically: ISP Telecom (~63%), Number Access (~29%). IRSF signature: 0% challenge completion rate + premium-rate country codes.

## Telesign Escalation

Telesign can: manually safelist specific phone numbers, adjust country risk thresholds, reset dynamic scoring. They send proactive notifications to IM when they detect anomalous spikes. For threshold changes, escalate to @aczeskis or @paulee.

## Related Skills

- `challenge-research` -- Broader challenge analysis including phone challenges, VoIP abuse, IRSF
- `challenge-events` -- SQL templates for challenge event queries
- `oncall-triage` -- General oncall triage starting point

## High-Cost SMS Geos (>$0.20/transaction)

Bhutan, Tajikistan, Madagascar, Uzbekistan, Syria, Sri Lanka, Azerbaijan, Togo, Burundi, Ethiopia. Average global SMS cost: ~$0.10/transaction.
