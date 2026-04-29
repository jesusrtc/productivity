# Reaction Spam Attack - Fake Account Triage

**Date:** 2026-04-09  
**Incident:** incident-11057  
**Slack:** [thread](https://linkedin-randd.slack.com/archives/C0AR8UVDB3P/p1775682032395049)  
**Reporter:** Kavita Malani (Feed SOT)  
**Assignee:** Katrina Wan (IM), jcortes (IM oncall)

## Summary

~16K+ fake accounts (member ID range 1.708B-1.725B) are hitting `voyagerSocialDashReactions` with CREATE REACT requests targeting `urn:li:activity:7401998949139865600` using incorrect activityUrn, causing 4xx errors in ~2.5hr burst cycles. Each member sends exactly 1 request per cycle (distributed pattern). QCS rate limiting is ineffective for this attack pattern.

## Step 1: Sample Account Profile

71 sample members from [paste 72027028](https://paste.corp.linkedin.com/show/72027028/) share identical registration signals:

| Attribute | Value |
|-----------|-------|
| Registration date | **All 2026-03-18** (04:31-08:41 UTC, tight 4hr window) |
| Country | **All US** |
| Email domain | **All Hotmail** |
| Connections | 0-1 (thin profiles) |
| Join IP | Null (proxied/scrubbed) |
| Tier | T3/T4 (per Kavita's manual review) |

100% of the sample is a single coordinated registration wave. False positive risk for mass action is negligible.

<details>
<summary>Query: dim_member_all profile</summary>

```sql
SET SESSION li_authorization_user = 'trustim';

SELECT is_restricted, restriction_type, country_code, 
  connection_count_bucket, domain, COUNT(*) as cnt
FROM prod_foundation_tables.dim_member_all
WHERE member_id IN (1708428281,1708429210,...,1708460963)
GROUP BY 1,2,3,4,5 ORDER BY cnt DESC
```
</details>

## Step 2: Restriction Timeline

![restriction-timeline.png](assets/restriction-timeline.png)

46/71 (65%) are restricted. 25/71 (35%) remain **active and unrestricted**. The bulk of restrictions happened Apr 2-4 via `nearline_ip_use_date_clustering` (30 accounts), with slower trickle from `profile-image-clustering` (8), `holistic_xgboost` (5), and `holistic_v3_decision` (3). Restriction velocity has stalled -- no new restrictions on Apr 9.

| Restriction Model | Count | Notes |
|-------------------|-------|-------|
| `nearline_ip_use_date_clustering` | 30 | IP-based, caught the bulk early |
| `profile-image-clustering` | 8 | FAKE_ACCOUNT reason |
| `online_holistic_xgboost` | 5 | Holistic scoring |
| `online_holistic_v3_decision` | 3 | Holistic scoring |
| **Unrestricted** | **25** | **Still active, evading all models** |

<details>
<summary>Query: restriction timeline</summary>

```sql
SELECT restriction_date, restriction_model_name,
  COUNT(DISTINCT member_id) as members
FROM prod_foundation_tables.dim_member_trust_restrictions
WHERE member_id IN (...)
  AND is_restricted = true
GROUP BY 1, 2 ORDER BY 1
```
</details>

## Step 3: QCS / UserRequestDenialEvent Check

QCS is **not triggering** for these members. The threshold is 20+ requests in 10 seconds per member, but each member sends only 1 request per ~2.5hr cycle. Sandeep confirmed: no sample members appear in `UserRequestDenialEvent`.

The QCS lix (`trex/test/2081585993`) was only 50% ramped; Dayananda activated to 100% on Apr 8. This is moot for the attack pattern -- even at 100%, the per-member threshold won't fire.

## Impact

Per Rui Han:
- Confirmed fake accounts with **0 connections, 0 invitations, 0 messages**
- **No trust DIHE impact**
- Impact is **service-side only**: inflated 4xx error rates on `voyagerSocialDashReactions`

## Conclusion

**This is a mass-action candidate.** All sample accounts are fake, from a single coordinated registration wave on Mar 18. Existing models caught 65% but velocity has stalled. The remaining 35% (extrapolated to ~5,600 of the 16K) continue generating 4xx errors every 2.5hrs.

### Recommended Actions

1. **Bulk restrict** the unrestricted accounts. Extract full member list from Kavita's Kusto query, push through ASTA or offline model:

```
voyager_api_feed_log_event
| where timestamp > datetime(2026-04-04T00:00:00Z)
| where logger == 'com.linkedin.voyager.dash.social.helpers.ErrorHelper'
| where message has 'REACT' and message has 'CREATE' 
  and message has 'urn:li:activity:7401998949139865600'
| extend memberId = tostring(loggingContext.memberId)
| summarize ErrorCount=count() by memberId
```

2. **Flag detection gap** to account abuse team: 35% evade `nearline_ip_use_date_clustering`, likely because join IPs are null/proxied.

3. **QCS won't help here.** For future distributed attacks, consider per-activityURN rate limiting (throttle when abnormal number of distinct members react to the same post).
