---
name: jss-dihe-investigation
description: >-
  Investigate Job Seeker Safety (JSS) DIHE/1k T7D spikes using Trino queries. Covers topline
  metric assessment, harm_type breakdown, tier/restriction_type drill-down, harm_sub_type analysis
  via flatten_harmful_experiences joined with JSS scoring, abuser profiling, and content analysis
  via UgcPostV2Event. Use when JSS DIHE alerts fire or Feed/Ads DIHE spikes are reported.
allowed-tools: Bash
---

# JSS DIHE Investigation

## How to Use This Skill

Use this skill when:
- A JSS DIHE/1k T7D alert fires (WoW spike detected)
- Someone reports a JSS DIHE elevation (e.g., via alert, Slack, or escalation)
- You need to drill down into Feed, Ads, or other harm_type DIHE spikes for Job Seekers
- You need to determine the root cause of a JSS DIHE spike — whether it stems from a data/pipeline issue, a new attack pattern, or an escalation of an existing attack

**Preamble:** `SET SESSION li_authorization_user = 'trustim';`

Other headless accounts: `ir2ato`, `ir2fake`, `ir2scraping`

**Partition format:** Varies by table — check each table's format before joining.

## SEV Thresholds for JSS DIHE/1k T7D

Per Neel's proposal, JSS DIHE/1k is treated as a True North metric:

| SEV 0 | SEV 1 | SEV 2 | SEV 3 | SEV 4 |
|-------|-------|-------|-------|-------|
| Only achievable with boosters | >45% | >30% | >25% | >20% |

**How to measure:** WoW % change = (Current T7D - Previous T7D) / Previous T7D

## Investigation Flow

Follow this sequence. Each step narrows the scope. Stop when you've identified the root cause.

### Step 1: Topline JSS DIHE/1k T7D — Confirm the Spike

**Dataset:** `u_tdsjobseeker.job_seeker_safety_dash_dihe`
**Level:** `JS_Score`

```sql
SELECT
    date_day,
    SUM(core_harmful_experience_t7d) as dihe_t7d,
    MAX(avg_active_users_t7d) as users_t7d,
    CAST(SUM(core_harmful_experience_t7d) AS DOUBLE)
        / NULLIF(MAX(avg_active_users_t7d), 0) * 1000 as dihe_per_1k_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'JS_Score'
    AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
    AND date_day >= DATE_ADD('day', -30, current_date)
GROUP BY date_day
ORDER BY date_day
```

**What to check:**
- Compute WoW % change for the latest date vs 7 days prior
- Check if active users changed (if flat, the spike is volume-driven)
- Compare against SEV thresholds above

### Step 2: Harm Type Breakdown — Which Harm Type Is Driving the Spike?

**Dataset:** `u_tdsjobseeker.job_seeker_safety_dash_dihe`
**Level:** `JS_Score__Harm_Type`

```sql
SELECT
    date_day,
    harm_type,
    SUM(core_harmful_experience_t7d) as dihe_t7d,
    MAX(avg_active_users_t7d) as avg_users_t7d,
    CAST(SUM(core_harmful_experience_t7d) AS DOUBLE)
        / NULLIF(MAX(avg_active_users_t7d), 0) * 1000 as dihe_per_1k_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'JS_Score__Harm_Type'
    AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
    AND date_day >= DATE_ADD('day', -30, current_date)
GROUP BY date_day, harm_type
ORDER BY date_day, harm_type
```

**Known harm_types:**
- `VIEWED_HOME_FEED_UPDATE` — Feed posts (original, reshared, viral)
- `VIEWED_AD` — Ads/sponsored content
- `VIEWED_FEED_COMMENT` — Feed comments
- `VIEWED_JOB` — Job postings
- `RECEIVED_INVITATION` — Connection invitations
- `RECEIVED_MESSAGE` — InMail/messages
- `VIEWED_GROUP_FEED_UPDATE` — Group posts (typically very low)

Compute WoW for each harm_type. Identify the top absolute mover(s).

### Step 3: Tier x Restriction Type — Which Tier Is Driving It?

**Dataset:** `u_tdsjobseeker.job_seeker_safety_dash_dihe`
**Level:** `Granular`

```sql
SELECT
    date_day, tier, restriction_type,
    core_harmful_experience_t7d as dihe_t7d,
    avg_active_users_t7d,
    CAST(core_harmful_experience_t7d AS DOUBLE)
        / NULLIF(avg_active_users_t7d, 0) * 1000 as dihe_per_1k_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'Granular'
    AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
    AND harm_type = '{HARM_TYPE_FROM_STEP_2}'
    AND date_day >= DATE_ADD('day', -30, current_date)
ORDER BY date_day, tier, restriction_type
```

**Tiers:** T1 (most severe) through T4 (least severe), plus ALL
**Restriction types:** ATO, Non-ATO, ALL

Compute WoW for each tier x restriction_type combination. Identify the segment with the largest absolute increase.

### Step 4: harm_sub_type Breakdown — What Specific Content Is Driving It?

**Dataset:** `u_trustim.flatten_harmful_experiences` joined with `u_jss.jss3_scoring`

This is where you get the granular content breakdown. The JSS dashboard tables don't have harm_sub_type — you need to join the raw DIHE events with the JSS member scope.

**Important:** Datepartition formats differ:
- `u_trustim.flatten_harmful_experiences`: `YYYY-MM-DD-00`
- `u_jss.jss3_scoring`: `YYYY-MM-DD`

Use `SUBSTR(he.datepartition, 1, 10) = js.datepartition` for the join.

**Key columns in flatten_harmful_experiences:**
- `memberid` = abuser ID
- `victim_id` = victim (the Job Seeker)
- `harm_sub_type` = specific content delivery mechanism
- `ato_yn` = 1 for ATO, 0 for non-ATO
- `core_yn` = 1 for core DIHE
- `harm_tier` = note: may be 0 in this table (tiering applied downstream)
- `entity_urn` = content URN
- `abuser_mlc`, `abuser_payment_status`, `is_abuser_premium` = abuser attributes

```sql
WITH jss_members AS (
    SELECT DISTINCT member_id, datepartition
    FROM u_jss.jss3_scoring
    WHERE jss_status IN (
        'Urgent Job Seeker',
        'Open To Job Seeker Look-alike',
        'Open To Job Seeker'
    )
    AND datepartition IN ('{CURRENT_DATE}', '{PREV_WEEK_DATE}')
)
SELECT
    he.datepartition,
    he.harm_sub_type,
    CASE WHEN he.ato_yn = 1 THEN 'ATO' ELSE 'Non-ATO' END as restriction_type,
    SUM(he.core_harmful_experience_7d_partial) as dihe_7d,
    COUNT(DISTINCT he.memberid) as unique_abusers,
    COUNT(DISTINCT he.victim_id) as unique_victims
FROM u_trustim.flatten_harmful_experiences he
JOIN jss_members js
    ON he.victim_id = js.member_id
    AND SUBSTR(he.datepartition, 1, 10) = js.datepartition
WHERE he.harm_type = '{HARM_TYPE_FROM_STEP_2}'
    AND he.core_yn = 1
    AND he.datepartition IN ('{CURRENT_DATE}-00', '{PREV_WEEK_DATE}-00')
GROUP BY he.datepartition, he.harm_sub_type,
    CASE WHEN he.ato_yn = 1 THEN 'ATO' ELSE 'Non-ATO' END
ORDER BY he.datepartition, dihe_7d DESC
```

**Common Feed harm_sub_types:**
- `ORIGINAL_IA_POST` — Original post by an Inauthentic Account
- `ORIGINAL_IA_GROUP_POST` — Original group post by an IA
- `VIRAL_ACTION_IA_POST` — Viral action (like/comment) on an IA post
- `POST_VIRAL_ACTION_BY_IA` — Post goes viral due to IA engagement
- `GROUP_POST_VIRAL_ACTION_BY_IA` — Group post viral via IA
- `RESHARED_IA_POST` — Reshared IA content
- `POST_RESHARED_BY_IA` — Post reshared by an IA
- `IA_PASSIVE_POST` — Passive IA post

IA = Inauthentic Account (flagged by Trust systems as operating inauthentically)

### Step 5: Abuser Profiling — Who Are the Top Abusers?

```sql
WITH jss_members AS (
    SELECT DISTINCT member_id, datepartition
    FROM u_jss.jss3_scoring
    WHERE jss_status IN (
        'Urgent Job Seeker',
        'Open To Job Seeker Look-alike',
        'Open To Job Seeker'
    )
    AND datepartition = '{CURRENT_DATE}'
)
SELECT
    he.memberid as abuser_id,
    SUM(he.core_harmful_experience_7d_partial) as dihe_7d,
    COUNT(DISTINCT he.victim_id) as victims,
    COUNT(*) as events,
    MAX(he.abuser_mlc) as abuser_mlc,
    MAX(he.abuser_payment_status) as payment_status,
    MAX(he.is_abuser_premium) as is_premium,
    MAX(he.abuser_reg_date_partition) as reg_date
FROM u_trustim.flatten_harmful_experiences he
JOIN jss_members js
    ON he.victim_id = js.member_id
    AND SUBSTR(he.datepartition, 1, 10) = js.datepartition
WHERE he.harm_type = '{HARM_TYPE}'
    AND he.harm_sub_type = '{HARM_SUB_TYPE_FROM_STEP_4}'
    AND he.ato_yn = {0_OR_1}
    AND he.core_yn = 1
    AND he.datepartition = '{CURRENT_DATE}-00'
GROUP BY he.memberid
ORDER BY dihe_7d DESC
LIMIT 20
```

**What to look for:**
- Abuser concentration: Do a few accounts drive most DIHE?
- MLC distribution: FourByFour = established/high-quality profiles
- Premium status: Are compromised Premium accounts involved?
- Registration date: None/old = likely ATO; recent = likely fake account

### Step 6: Abuser Overlap — New vs Recurring

Check if the abusers are new this week or recurring from prior weeks:

```sql
WITH jss_members AS (
    SELECT DISTINCT member_id, datepartition
    FROM u_jss.jss3_scoring
    WHERE jss_status IN (
        'Urgent Job Seeker',
        'Open To Job Seeker Look-alike',
        'Open To Job Seeker'
    )
    AND datepartition IN ('{CURRENT_DATE}', '{PREV_WEEK_DATE}')
),
curr_abusers AS (
    SELECT DISTINCT he.memberid
    FROM u_trustim.flatten_harmful_experiences he
    JOIN jss_members js ON he.victim_id = js.member_id
        AND SUBSTR(he.datepartition, 1, 10) = js.datepartition
    WHERE he.harm_type = '{HARM_TYPE}'
        AND he.harm_sub_type = '{HARM_SUB_TYPE}'
        AND he.ato_yn = {0_OR_1} AND he.core_yn = 1
        AND he.datepartition = '{CURRENT_DATE}-00'
),
prev_abusers AS (
    SELECT DISTINCT he.memberid
    FROM u_trustim.flatten_harmful_experiences he
    JOIN jss_members js ON he.victim_id = js.member_id
        AND SUBSTR(he.datepartition, 1, 10) = js.datepartition
    WHERE he.harm_type = '{HARM_TYPE}'
        AND he.harm_sub_type = '{HARM_SUB_TYPE}'
        AND he.ato_yn = {0_OR_1} AND he.core_yn = 1
        AND he.datepartition = '{PREV_WEEK_DATE}-00'
)
SELECT
    (SELECT COUNT(*) FROM curr_abusers) as current_week_abusers,
    (SELECT COUNT(*) FROM prev_abusers) as prev_week_abusers,
    (SELECT COUNT(*) FROM curr_abusers c
     JOIN prev_abusers p ON c.memberid = p.memberid) as recurring,
    (SELECT COUNT(*) FROM curr_abusers c
     LEFT JOIN prev_abusers p ON c.memberid = p.memberid
     WHERE p.memberid IS NULL) as new_this_week
```

**Interpretation:**
- Mostly new abusers → fresh attack wave / new compromised accounts
- Mostly recurring → ongoing campaign not being caught
- Mix → evolving campaign with persistent + new accounts

### Step 7: Content Analysis — What Are They Posting?

**Dataset:** `tracking.UgcPostV2Event`

```sql
WITH abusers AS (
    -- Use top abuser IDs from Step 5
    SELECT DISTINCT he.memberid as abuser_id
    FROM u_trustim.flatten_harmful_experiences he
    WHERE he.harm_type = '{HARM_TYPE}'
        AND he.harm_sub_type = '{HARM_SUB_TYPE}'
        AND he.ato_yn = {0_OR_1} AND he.core_yn = 1
        AND he.datepartition = '{CURRENT_DATE}-00'
    GROUP BY he.memberid
    ORDER BY SUM(he.core_harmful_experience_7d_partial) DESC
    LIMIT 50
)
SELECT
    e.posturn,
    e.containerentityurn,
    e.lifecyclestate,
    e.visibility,
    SUBSTR(e.postcontent.commentary.text, 1, 300) as text_preview,
    e.postcontent.content.content.ingestedcontent.ingestedurl as url,
    e.postcontent.content.content.mediacontent.mediatype as media_type,
    from_unixtime(e.created.time / 1000) as created_at
FROM tracking.UgcPostV2Event e
INNER JOIN abusers a
    ON e.authorurn = 'urn:li:member:' || CAST(a.abuser_id AS VARCHAR)
WHERE e.datepartition >= '{RECENT_DATE}-00'
    AND e.lifecyclestate IN ('PUBLISHED', 'PUBLISH_SUCCEEDED')
ORDER BY e.created.time DESC
LIMIT 30
```

**What to extract:**
- Post text templates (look for copy-paste patterns)
- Email addresses / domains (scam contact info)
- Container URNs (which Groups are being targeted)
- Media types (text-only = harder to detect)
- Posting velocity (same content across N groups in M minutes)

**Top Groups query:**

```sql
-- Same abusers CTE as above, then:
SELECT
    e.containerentityurn as group_urn,
    COUNT(DISTINCT e.posturn) as posts,
    COUNT(DISTINCT e.authorurn) as authors
FROM tracking.UgcPostV2Event e
INNER JOIN abusers a
    ON e.authorurn = 'urn:li:member:' || CAST(a.abuser_id AS VARCHAR)
WHERE e.datepartition >= '{RECENT_DATE}-00'
    AND e.lifecyclestate IN ('PUBLISHED', 'PUBLISH_SUCCEEDED')
    AND e.containerentityurn LIKE 'urn:li:group:%'
GROUP BY e.containerentityurn
ORDER BY posts DESC
LIMIT 20
```

### Step 8: Cross-Validate with Reports

**Dataset:** `u_tdsjobseeker.job_seeker_safety_dash_reports`

```sql
SELECT
    date_day, content_source,
    SUM(num_user_flagged_event_t7d) as reports_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_reports
WHERE jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
    AND content_source != 'ALL'
    AND date_day >= DATE_ADD('day', -30, current_date)
GROUP BY date_day, content_source
ORDER BY date_day, content_source
```

**Content sources:** COMPANIES, GROUPS_POST, INBOX_MESSAGE_BETWEEN_CONNECTIONS, INBOX_PROPOSAL, INBOX_REPLY, OTHER, PROFILE, SAS_SPONSORED_UPDATE, SPONSORED_INMAIL, SPONSORED_MESSAGE, UGC_POST, USCP_COMMENT

**Interpretation:**
- Reports spiking in parallel with DIHE → attack is visible to users, defenses may be slow
- Reports NOT spiking → detection gap (content not being reported/caught), or the attack is stealthy (text-only, no links)

## Data Issue vs Real Abuse Checklist

Before concluding root cause, check:

| Signal | Data Issue | Real Abuse |
|--------|-----------|------------|
| Abuser overlap WoW | Same abusers, unchanged | New abusers appearing |
| Abuser concentration | Evenly distributed | Few accounts = most DIHE |
| Content confirmed | No content found / gibberish | Actual harmful content (scams, spam) |
| Active users | Changed (pipeline change) | Flat |
| Reports correlation | Uncorrelated / anti-correlated | Correlated or detection gap |
| Timing | Aligns with pipeline deploy | Aligns with no known changes |

## Key Tables Reference

| Table | Datepartition Format | Key Columns | Notes |
|-------|---------------------|-------------|-------|
| `u_tdsjobseeker.job_seeker_safety_dash_dihe` | date column (`date_day`) | level, harm_type, tier, restriction_type, core_harmful_experience_t7d, avg_active_users_t7d | Dashboard table. Levels: JS_Score, JS_Score__Harm_Type, Granular |
| `u_trustim.flatten_harmful_experiences` | `YYYY-MM-DD-00` | memberid (abuser), victim_id, harm_type, harm_sub_type, ato_yn, core_yn, entity_urn, abuser_mlc | Raw event-level DIHE. harm_tier may be 0 (tiering applied downstream) |
| `u_jss.jss3_scoring` | `YYYY-MM-DD` | member_id, jss_status, datepartition | JSS member scope. Join on victim_id = member_id |
| `tracking.UgcPostV2Event` | `YYYY-MM-DD-00` | authorurn, posturn, containerentityurn, postcontent.commentary.text, created.time | Post content. Join on authorurn = 'urn:li:member:' + abuser_id |
| `u_tdsjobseeker.job_seeker_safety_dash_reports` | date column (`date_day`) | level, flagging_reason, content_source, tier, num_user_flagged_event_t7d | Reports cross-validation |

## JSS Status Mapping

When joining with `u_jss.jss3_scoring`, use these statuses for the core JSS population:
- `'Urgent Job Seeker'`
- `'Open To Job Seeker'`
- `'Open To Job Seeker Look-alike'` (maps to `'Open To Job Seeker'` in grouped)

For broader analysis, also include:
- `'Opportunistic Job Seeker'`
- `'Opportunistic Job Seeker Look-alike'`

## Output Template

After completing the investigation, produce a summary with:

1. **Topline**: JSS DIHE/1k T7D WoW % change and SEV level
2. **Primary driver**: Which harm_type, tier, restriction_type
3. **Root cause**: harm_sub_type, ATO vs non-ATO, abuser profile
4. **Content**: What is being posted (templates, scam emails, targeted Groups)
5. **Evidence it's real**: New abusers, content confirmed, reports cross-validation
6. **Merge decision**: Same population/MO as existing SEVs? Merge or keep separate
7. **Recommended next steps**: Enforcement actions, monitoring, escalation
