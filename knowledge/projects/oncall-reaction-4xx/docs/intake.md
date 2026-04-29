# Intake: Bot Reaction-Create Attack on Invalid Activity URN

## What is happening

Approximately 25,120 bot accounts (member IDs 1.708B-1.725B, tiers T3/T4) are repeatedly sending REACTION_CREATE requests to an invalid activity URN (`urn:li:activity:7401998949139865600`), generating consistent 4xx errors from SAP (Social Action Platform). The attack has been ongoing since approximately Apr 3. The bots evade QCS rate limiting by staying under the 20-hit/10-second threshold -- each member fires exactly 1 error per ~2.5h retry cycle. A majority of accounts are already restricted by other defense systems (IP clustering, profile image clustering, fake account model), and the team is asking whether to mass restrict the remaining ~25K accounts.

## Spike Confirmation

### Overview

![Daily 404 Errors](plot_daily_errors.png)

![Hourly Burst Pattern](plot_hourly_bursts.png)

![QCS Effectiveness](plot_qcs_effectiveness.png)

![Restriction Status](plot_restriction_status.png)

### Primary Table: service.voyager_api_feed_log_event (ACCESS DENIED)

The reporter's original data comes from the `voyager_api_feed_log_event` service log table, queried via Kusto. This table is not accessible via any of our Trino headless accounts (`ir2fake`, `trustim`, `far`, `tdsfake`, `tdsfraud`). The Kusto endpoint was also unavailable during this intake. Requires joining group `gr003710` for permanent Trino access.

**Reporter's Kusto query (unverified -- cannot replicate):**
```kql
voyager_api_feed_log_event
  | where timestamp > datetime(2026-04-04T00:00:00Z)
  | where logger == 'com.linkedin.voyager.dash.social.helpers.ErrorHelper'
  | where message has 'threadUrn' and message has 'REACT' and message has 'CREATE'
    and message has 'urn:li:activity:7401998949139865600'
  | extend memberId = tostring(loggingContext.memberId)
  | summarize ErrorCount=count() by memberId
```

### Partial Confirmation via tracking.userrequestevent

The `tracking.userrequestevent` table captures only a sampled subset of requests. We found ~3% of the reported volume, but the pattern characteristics match.

**Query used:**
```sql
SET SESSION li_authorization_user = 'trustim';

SELECT datepartition,
       response.statuscode,
       COUNT(*) AS request_count,
       COUNT(DISTINCT COALESCE(header.memberidv2, CAST(header.memberid AS BIGINT))) AS distinct_members
FROM tracking.userrequestevent
WHERE datepartition >= '2026-04-03-00' AND datepartition <= '2026-04-09-00'
  AND request.path LIKE '%reaction%'
  AND response.statuscode BETWEEN 400 AND 499
  AND COALESCE(header.memberidv2, CAST(header.memberid AS BIGINT)) BETWEEN 1708000000 AND 1725000000
GROUP BY datepartition, response.statuscode
ORDER BY datepartition, response.statuscode
```

**Results (sampled -- represents ~3% of actual volume):**

| Date       | Status | Requests | Distinct Members |
|------------|--------|----------|------------------|
| 2026-04-03 | 404    | 237      | 183              |
| 2026-04-03 | 429    | 33       | 2                |
| 2026-04-04 | 404    | 52       | 45               |
| 2026-04-05 | 404    | 248      | 215              |
| 2026-04-06 | 404    | 429      | 251              |
| 2026-04-07 | 404    | 349      | 275              |
| 2026-04-07 | 429    | 22       | 3                |
| 2026-04-08 | 404    | 394      | 298              |

**Key findings:**
- 823 distinct bot member IDs found (sampled), ranging from MID 1,708,017,281 to 1,724,615,818 -- matching the reported 1.708B-1.725B range
- Request path: `voyager/api/feed/reactions` -- confirms reaction endpoint
- Dominant error: 404 (invalid activity URN) -- consistent with report
- Small number of 429s (rate limit) from only 2-3 members -- confirms QCS is NOT broadly triggering

### Hourly Burst Pattern (Apr 7 sample)

| Hour (UTC) | Errors | Distinct Members |
|------------|--------|------------------|
| 07:00      | 3      | 3                |
| 08:00      | 59     | 57               |
| 09:00      | 7      | 7                |
| 12:00      | 23     | 22               |
| 14:00      | 26     | 17               |
| 17:00      | 23     | 22               |
| 20:00      | 79     | 75               |
| 22:00      | 18     | 13               |

The spiky hourly pattern with ~2-3h gaps between bursts is consistent with the reported ~2.5h retry cycle.

### QCS Denial Confirmation

```sql
SELECT COUNT(*) AS denial_count, COUNT(DISTINCT header.memberid) AS distinct_members
FROM tracking.userrequestdenialevent
WHERE datepartition >= '2026-04-03-00' AND datepartition <= '2026-04-09-00'
  AND header.memberid BETWEEN 1708000000 AND 1725000000
  AND request.path LIKE '%reaction%'
```

**Result:** 75 total denials, 8 distinct members. Confirms QCS is almost completely failing to trigger on these bots.

### Restriction Status of Identified Bot Accounts

From the 720 bot accounts found via `tracking.userrequestevent` (Apr 5-9):
- **Restricted:** 168 (23%)
- **Unrestricted:** 552 (77%)

Top restriction model for restricted accounts: `garnet_offline` (offline fake account detection model). The lower restriction rate (23% vs reporter's 69%) is likely due to the `userrequestevent` sample capturing a different subset than the reporter's manual sample.

Sample of 30 accounts with restriction details confirms mix of restricted (via `garnet_offline`) and unrestricted accounts, with member IDs spread across the reported range.

### Spike Confirmation Summary

- **Magnitude match:** Cannot fully confirm 25,120 accounts due to access limitations on `service.voyager_api_feed_log_event`. The 823 accounts found in `tracking.userrequestevent` represent a sampled subset (~3%). Pattern characteristics match.
- **Member ID range:** Confirmed (1,708,017,281 to 1,724,615,818)
- **Error type:** Confirmed (404 on `voyager/api/feed/reactions`)
- **QCS bypass:** Confirmed (only 8 members received denials across 7 days)
- **Burst pattern:** Consistent with reported 2.5h retry cycles
- **Restriction status:** Partially confirmed (23% restricted in our sample; reporter claims 69% in their manual sample)

## True North Metric

**Metric: 404 error count on `voyager/api/feed/reactions` for MID range 1.708B-1.725B**

This is the single metric that captures the attack. There is only one spike reported (reaction-create 4xx errors), so no containment analysis is needed. The QCS denial count is NOT a useful anchor because QCS is failing to detect these bots -- the absence of denials IS the problem.

The ideal data source is `service.voyager_api_feed_log_event` (the reporter's original table), but access is required. The `tracking.userrequestevent` table provides directional confirmation only.

## Context

- **SAP (Social Action Platform):** LinkedIn's backend service that handles social actions on the feed -- reactions (likes, celebrates, etc.), comments, and shares. When a member clicks "Like" on a post, the request goes to SAP. In this case, SAP returns 4xx because the target activity URN is invalid.

- **QCS (Quality Control Service):** LinkedIn's rate-limiting / quality control system that sits in front of various services. Uses counter-based rules (e.g., "if member makes 20+ requests in 10 seconds, throttle"). The bots in this attack stay under the threshold by firing exactly 1 request per member per ~2.5h cycle. A lix controlling the QCS counter was only 50% ramped, meaning ~50% of traffic may not have been counted.

- **Lix:** LinkedIn's experiment and feature flag system. Used to ramp features gradually (0% -> 50% -> 100%). In this incident, a lix guarding the QCS reaction counter was at 50% ramp, meaning the counter was not incrementing for half the traffic. A new 100% iteration was created Mar 30 but not activated until during this incident.

- **T3/T4 (Account Tiers):** LinkedIn member account tiers based on engagement and activity. T3 and T4 are low-engagement tiers, typically associated with new, inactive, or suspicious accounts. Legitimate active members are usually T1 or T2.

- **Activity URN:** LinkedIn's universal resource name format for feed items (posts, articles, shares). Format: `urn:li:activity:{id}`. The URN `urn:li:activity:7401998949139865600` is invalid -- it does not correspond to any real feed item, which is why SAP returns 404.

- **DIHE (Detected Inauthentic Harmful Experience):** LinkedIn's primary metric for measuring harm caused by inauthentic (fake/compromised) accounts. Measures unique real members who received harmful content (spam messages, fake invitations, etc.) from restricted accounts. The team confirmed no expected DIHE impact since these bots are hitting an invalid URN and producing no user-visible harm.

- **UserRequestDenialEvent:** A tracking event fired when QCS denies/blocks a request. The absence of these events for the bot accounts confirms QCS is not triggering.

- **Feed SOT (Source of Truth) team:** The LinkedIn team responsible for the feed service, including reactions, comments, and content delivery.

- **voyagerSocialDashReactions:** An InGraph metric tracking reaction-related requests in the Voyager API feed service. The reporter shared a screenshot showing spiky error patterns on this metric.

- **garnet_offline:** An offline fake account detection model used by LinkedIn's trust systems. One of several models that restrict accounts after detection (as opposed to real-time scoring).

- **IP clustering / Profile image clustering:** Offline batch processes that identify coordinated fake account creation by finding accounts that share IP addresses at registration or use the same profile images. These models had already restricted 49/71 of the reporter's sampled accounts.

## Mappings

- `voyager_api_feed_log_event` (Kusto) -> `service.voyager_api_feed_log_event` (Trino, ACCESS DENIED) -- same table name in `service` schema; found by matching Kusto table name to Trino `service.*` catalog
- `voyagerSocialDashReactions` (InGraph metric) -> no direct Trino table; this is an operational metric derived from `voyager-api-feed` service logs
- Reaction 4xx errors -> `tracking.userrequestevent` where `request.path LIKE '%reaction%' AND response.statuscode BETWEEN 400 AND 499` (Trino, partial/sampled); found by searching tracking tables for request-level data
- QCS denials -> `tracking.userrequestdenialevent` where `request.path LIKE '%reaction%'` (Trino, accessible via `trustim`); found in `common-reference/SKILL.md`
- Account restrictions -> `data_derived.member_restrictions` (Trino, accessible via `trustim`); found in `common-reference/SKILL.md`
- Restriction history with sources -> `prod_foundation_tables.dim_member_trust_restrictions` (Trino, accessible via `trustim`); found in `common-reference/SKILL.md`
- `tracking.FuseCounterActionEvent` -> QCS counter actions (Trino, ACCESS DENIED for both `ir2fake` and `trustim`)
- `tracking.registrationevent` -> registration data (Trino, ACCESS DENIED for `ir2fake`)

## Access Issues

| Table | Error | Source | Priority | Query Attempted |
|-------|-------|--------|----------|-----------------|
| `service.voyager_api_feed_log_event` | Access denied. Requires group `gr003710`. | intake | critical | `SELECT datepartition, COUNT(*) ... FROM service.voyager_api_feed_log_event WHERE logger = 'com.linkedin.voyager.dash.social.helpers.ErrorHelper' AND message LIKE '%REACT%' AND message LIKE '%CREATE%' AND message LIKE '%urn:li:activity:7401998949139865600%' ...` |
| `tracking.userrequestdenialevent` | Access denied for `ir2fake` headless. Works with `trustim`. | local | high | `DESCRIBE tracking.userrequestdenialevent` |
| `tracking.FuseCounterActionEvent` | Access denied for both `ir2fake` and `trustim` headless accounts. | local | high | `DESCRIBE tracking.FuseCounterActionEvent` |
| `tracking.registrationevent` | Access denied for `ir2fake` headless. Not tested with `trustim`. | local | high | `SELECT ... FROM tracking.registrationevent WHERE ... member_id BETWEEN 1708000000 AND 1725000000 ...` |
| `prod_foundation_tables.dim_member_trust_restrictions` | Access denied for `ir2fake`. Works with `trustim`. | local | high | `DESCRIBE prod_foundation_tables.dim_member_trust_restrictions` |

## Open Questions

1. **Cannot fully replicate the 25K account count.** The primary data source (`service.voyager_api_feed_log_event`) is access-denied in Trino for all available headless accounts, and the Kusto endpoint was unreachable during this intake. We found 823 accounts via the sampled `tracking.userrequestevent` table. **To fully confirm the 25K number, we need either: (a) access to `service.voyager_api_feed_log_event` via Trino group `gr003710`, or (b) access to the Kusto cluster for `voyager-api-feed`.**

2. **Restriction rate discrepancy.** We found 23% restricted vs the reporter's 69%. This is likely a sampling difference (our `userrequestevent` sample is a different subset than the reporter's manual sample of 71 accounts), but should be verified once full account list is available.

3. **Lix details.** The intake mentions a lix guarding the QCS counter was 50% ramped, with a 100% iteration created Mar 30. The specific lix name was not provided. Knowing the lix name would allow querying `data_derived_column.lixexperimentassignmentdata_daily` to confirm what percentage of the bot accounts were in the control group.

4. **Current status of the lix ramp.** The intake says the 100% iteration was "not activated until during this incident" -- it is unclear whether the lix is now fully ramped and whether QCS is now catching these bots.
