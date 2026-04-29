# Drop in Cold Registrations — April 8, 2026

## Context

Slack thread: https://linkedin-randd.slack.com/archives/C0AJRL0GSR3/p1775728078004559

From Slack thread in #incident-11066:

- **Patricia O'Meara** reported signup drop starting ~6:30 PM PT on April 8. Double-digit drop from 6 PM–11 PM hours.
- **Zihua Liu** confirmed no changes from reg side.
- **Tomas Valdivia Hennig** confirmed no reg model changes yesterday.
- **Jesus Talamantes** confirmed the traffic caught by the rule was abusive.
- Previous incident-11066 context: a new reactive reg model was ramped that blocked suspicious/bot activity, then reverted, causing signups to bounce back. Now seeing another drop — unclear if re-ramped or if defenses kicked in organically.
- **Conclusion so far**: the dip appears related to previously mentioned bot activity and defenses kicking in. w/4w comparison looks inline.

## Metric Anchor

| Field | Value |
|-------|-------|
| Table | `tracking.scoreeventforregistration` |
| Expression | `COUNT(*)` (registration attempts) |
| Filters | `scorerstage = 'CURRENT' AND params['registration_type'] = 'COLD' AND params['reg_input_data_validation'] = 'VALID'` |
| Baseline | w/4w (March 11–12) and w/1w (April 1–2) |
| Spike (drop) | April 8 18:00 PT onward |

## Goals

1. Confirm the cold registration drop starting ~6:30 PM PT April 8
2. Determine if the drop is in attempts (scoreevent) or successful registrations or both
3. Attribute the drop — break down by challenge type, model score, and signals to identify what's blocking
4. Confirm whether this is the reactive reg model re-ramp or organic defense behavior
5. Compare w/4w to assess if current levels are back to pre-bot-attack baseline

---

## Investigation

### Step 1: Confirm the drop in cold registration attempts

Hourly cold registration attempts (PT), April 7 vs April 8 evening:

| Hour (PT) | April 7 | April 8 | Delta |
|-----------|---------|---------|-------|
| 17:00 | 86,025 | 69,067 | -20% |
| 18:00 | 169,390 | 63,160 | **-63%** |
| 19:00 | 166,539 | 58,100 | **-65%** |
| 20:00 | 163,221 | 58,242 | **-64%** |
| 21:00 | 144,218 | 60,753 | **-58%** |

The evening surge that existed on April 7 (peaking at 169K/hr) completely disappeared on April 8 (flat at ~60K/hr).

![cold-reg-bot-vs-other.png](assets/cold-reg-bot-vs-other.png)

The chart tells the full story: bot traffic (red, evercaptcha-challenged) surged Apr 4-5, persisted through Apr 7, then vanished on Apr 8 evening. The blue "Other" layer (legitimate + other challenge traffic) is stable throughout.

<details><summary>Query</summary>

```sql
SELECT date_format(from_unixtime((header.time / 1000), 'America/Los_Angeles'), '%Y-%m-%d %H:00') as hour_pt,
       COUNT(*) as attempts
FROM tracking.scoreeventforregistration
WHERE datepartition >= '2026-04-07-00' AND datepartition <= '2026-04-09-23'
  AND scorerstage = 'CURRENT'
  AND params['registration_type'] = 'COLD'
  AND params['reg_input_data_validation'] = 'VALID'
GROUP BY 1 ORDER BY 1 ASC
```
</details>

### Step 2: Drop is in failed attempts, not successful registrations

Comparing attempts vs successful registrations at 18:00 PT:

| Metric | April 7 | April 8 | Delta |
|--------|---------|---------|-------|
| Attempt Only (no registration) | 145,263 | 34,277 | **-76%** |
| Registered (success) | 24,127 | 28,883 | **+20%** |
| Total | 169,390 | 63,160 | -63% |

**The actual successful registrations are stable or slightly up.** The entire drop is in attempts that never completed registration — i.e., bot/suspicious traffic that was being challenged and failing.

![registration-success.png](assets/registration-success.png)

Successful registrations from `tracking.registrationevent` show a normal daily pattern throughout Apr 1-9. The only real dip was Apr 2 when the reactive reg model was initially ramped (orange annotation). Apr 8 evening (green highlight) is at ~24-27K/hr — completely normal for that time of day.

<details><summary>Query</summary>

```sql
SELECT date_format(from_unixtime((se.header.time / 1000), 'America/Los_Angeles'), '%Y-%m-%d %H:00') as hour_pt,
       CASE WHEN r.submissionid IS NOT NULL THEN 'Registered' ELSE 'Attempt Only' END as label,
       COUNT(*) as cnt
FROM tracking.scoreeventforregistration se
LEFT JOIN tracking.registrationevent r
  ON r.datepartition = se.datepartition AND r.submissionid = se.submissionid
  AND r.datepartition >= '2026-04-07-00' AND r.datepartition <= '2026-04-09-23'
WHERE se.datepartition >= '2026-04-07-00' AND se.datepartition <= '2026-04-09-23'
  AND se.scorerstage = 'CURRENT'
  AND se.params['registration_type'] = 'COLD'
  AND se.params['reg_input_data_validation'] = 'VALID'
GROUP BY 1, 2 ORDER BY 1 ASC, 2
```
</details>

### Step 3: Evercaptcha is the driver — bot traffic stopped

Challenge type breakdown at 18:00 PT:

| Challenge Type | April 7 | April 8 | Delta |
|----------------|---------|---------|-------|
| evercaptcha | 100,524 | 17,964 | **-82%** |
| Phone Challenge | 25,833 | 7,886 | -69% |
| Captcha Challenge | 21,989 | 10,977 | -50% |
| No Challenge | 21,044 | 26,333 | +25% |

**Evercaptcha dropped by 82K attempts/hr** — this accounts for ~78% of the total drop. The evening surge on April 7 was almost entirely bot traffic hitting evercaptcha challenges and failing. On April 8 evening, evercaptcha is back to baseline (~18K), consistent with the bot traffic being gone.

"No Challenge" (legitimate traffic) actually increased, confirming real users are unaffected.

<details><summary>Query</summary>

```sql
SELECT date_format(from_unixtime((header.time / 1000), 'America/Los_Angeles'), '%Y-%m-%d %H:00') as hour_pt,
       CASE WHEN element_at(params, 'ignore_ratio') = '1.0'
                 AND lower(coalesce(element_at(params, 'challenge_type'), '')) LIKE '%captcha%'
            THEN 'evercaptcha'
            ELSE coalesce(element_at(params, 'challenge_type'), 'none')
       END as challenge_type,
       COUNT(*) as cnt
FROM tracking.scoreeventforregistration
WHERE datepartition >= '2026-04-07-00' AND datepartition <= '2026-04-09-23'
  AND scorerstage = 'CURRENT'
  AND params['registration_type'] = 'COLD'
  AND params['reg_input_data_validation'] = 'VALID'
GROUP BY 1, 2 ORDER BY 1 ASC, 3 DESC
```
</details>

## Conclusion

The cold registration drop starting ~6:30 PM PT on April 8 is **not a drop in real signups**. It's the disappearance of bot traffic that was inflating registration attempt counts.

- The evening surge on April 7 was ~100K/hr of evercaptcha-challenged bot attempts
- On April 8, that bot traffic stopped, returning attempt volumes to organic baseline
- Actual successful registrations are stable/up (+20% at 18:00 PT)
- No reg model was re-ramped (confirmed by Tomas). The bots simply stopped attacking
- **w/4w comparison is the right baseline** — the elevated w/w numbers from last week included bot traffic that has now been suppressed

**Action**: No anti-abuse action needed. This is a positive signal — bot traffic subsiding. Growth team should compare to w/4w for clean baseline.
