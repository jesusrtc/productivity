# JSS Feed DIHE Investigation

**Date:** 2026-04-08 | **Oncall IM:** Jesus Talamantes | **Investigator:** Jesus Cortes
**Source table:** `u_tdsjobseeker.job_seeker_safety_dash_dihe` (JSS Open + Urgent Job Seekers)
**Main chart:** `level = 'JS_Score__Harm_Type'`, `harm_type = 'VIEWED_HOME_FEED_UPDATE'`

---

## 1. Driver: VIEWED_HOME_FEED_UPDATE

VIEWED_HOME_FEED_UPDATE is the sole driver of the JSS DIHE spike (+3.4M, +40.6% WoW). All other harm_types are stable or declining.

![JSS DIHE T7D by Harm Type](assets/harm_type_trend.png)

<details><summary>Query</summary>

```sql
SELECT date_day, harm_type, SUM(core_harmful_experience_t7d) AS dihe_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'JS_Score__Harm_Type'
  AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
  AND date_day >= DATE '2026-02-01'
GROUP BY date_day, harm_type
ORDER BY date_day, harm_type
```
</details>

---

## 2. ATO is driving the Feed increase

ATO doubled from 2.77M to 5.56M (+100.9%) in 7 days (Mar 23-30), while Non-ATO rose modestly from 5.54M to 6.68M (+20.7%). ATO accounts for **70.9% of the total Feed DIHE increase** from trough to peak. ATO baseline (Feb 15 - Mar 16) was 3.79M; the Mar 30 peak of 5.56M is 46.7% above baseline.

![JSS Feed DIHE: ATO vs Non-ATO](assets/jss_feed_ato_vs_nonato.png)

<details><summary>Query</summary>

```sql
SELECT date_day, restriction_type, SUM(core_harmful_experience_t7d) AS dihe_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'Granular'
  AND harm_type = 'VIEWED_HOME_FEED_UPDATE'
  AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
  AND date_day >= DATE '2026-02-01'
GROUP BY date_day, restriction_type
ORDER BY date_day, restriction_type
```
</details>

---

## 3. ATO spike concentrated in T1 and T2

Within ATO, T1 and T2 account for **93.3% of the increase** from trough to peak. T2 has been the dominant tier since early March and is the single largest contributor at 40.1% of ATO increase. T3/T4 are essentially flat.

| Tier | Trough (Mar 23) | Peak (Mar 30) | Change | Share of ATO increase |
|------|-----------------|---------------|--------|-----------------------|
| T1 | 0.82M | 2.31M | +180.7% | 53.3% |
| T2 | 1.34M | 2.45M | +83.7% | 40.1% |
| T3 | 0.47M | 0.64M | +36.8% | 6.2% |
| T4 | 0.14M | 0.16M | +10.5% | 0.5% |

![JSS Feed DIHE: ATO by Tier](assets/jss_feed_ato_by_tier.png)

<details><summary>Query</summary>

```sql
SELECT date_day, tier, SUM(core_harmful_experience_t7d) AS dihe_t7d
FROM u_tdsjobseeker.job_seeker_safety_dash_dihe
WHERE level = 'Granular'
  AND harm_type = 'VIEWED_HOME_FEED_UPDATE'
  AND jss_status_grouped IN ('Open To Job Seeker', 'Urgent Job Seeker')
  AND restriction_type = 'ATO'
  AND date_day >= DATE '2026-02-15'
GROUP BY date_day, tier
ORDER BY date_day, tier
```
</details>

---

## 4. CS Audit: What the ATO accounts are doing

Sampled the top 20 ATO Feed abusers by DIHE (Mar 23-30 spike window) and checked their CS audit trail. Clear ATO campaign pattern:

**Takeover sequence:** Attackers solve ATO challenges at 90.9% rate (52/57 shown vs solved), including email PIN challenges -- indicating they have access to the victim's email. 15 of 20 accounts changed passwords via email link, locking out the real owner.

**Post-takeover modifications:** Profile changes (headline: 3 MIDs, job: 2 MIDs, summary: 5 MIDs, photo: 2 MIDs) to make the account look legitimate before posting scam content.

**Defense gap:** 2 accounts triggered `ATTEMPTED_RESTRICTION_BUT_WHITELISTED` (6 events) -- the system tried to restrict them but they were whitelisted. 1 account has 162 SIP violations without being stopped.

**Restriction notes reveal Ads SEV overlap:** The restriction notes on MIDs 426298907 and 739801037 read: *"JSS March 2026 — ATO remediation for 307 compromised accounts used as BZM co-admins on Zambia fake ad accounts. Invalidate pwd + logout sessions."* This was a **manual batch action** (`JSS-Zambia-ATO-coadmin-pwdreset`) executed on **Mar 30** — the last day of the spike window. These are the same actors as the ongoing Ads SEV 3 (Zambia fake ad accounts). The top abuser by DIHE (MID 412977836) was **never restricted** during the spike window — only M2M blocks on other members. All Feed DIHE from these accounts accrued unmitigated until the manual takedown.

| Event | Count | MIDs | Interpretation |
|-------|-------|------|---------------|
| SIP_VIOLATION_DETECTED | 162 | 1 | Repeat offender not caught |
| SHOWN_EMAIL_PIN_CHALLENGE | 111 | 11 | System challenged them |
| SHOWN_ATO_SUPER_CHALLENGE | 79 | 11 | Flagged as ATO |
| SOLVED_ATO_SUPER_CHALLENGE | 52 | 10 | 90.9% solve rate |
| SOLVED_EMAIL_PIN_CHALLENGE | 41 | 10 | Have email access |
| SET_LOGIN_MEMBER_RESTRICTION | 19 | 15 | Eventually restricted |
| SET_SPAM_RESTRICTION | 18 | 15 | Eventually restricted |
| CHANGE_PASSWORD_FROM_EMAIL | 15 | 8 | Locking out real owner |
| LOGIN_FAILURE_WRONG_PASSWORD | 13 | 6 | Credential stuffing |
| PROFILE_HEADLINE/JOB/SUMMARY_CHANGED | 19 | 5+ | Account modification |
| ATTEMPTED_RESTRICTION_BUT_WHITELISTED | 6 | 2 | Defense bypass |

<details><summary>Query</summary>

```sql
-- Step 1: Top 20 ATO Feed abusers by DIHE
SELECT abuser_id, SUM(core_harmful_experience_7d_partial) AS dihe
FROM u_metrics.account_abuse_harmful_experience_union
WHERE harm_type = 'VIEWED_HOME_FEED_UPDATE'
  AND ato_yn = 1 AND core_yn = 1
  AND datepartition >= '2026-03-23-00' AND datepartition <= '2026-03-30-00'
GROUP BY abuser_id ORDER BY dihe DESC LIMIT 20

-- Step 2: CS audit for those MIDs
SELECT event_type, COUNT(*) AS cnt, COUNT(DISTINCT memberid) AS mids
FROM u_trustim.event_cs_audit
WHERE memberid IN (<top 20 MIDs>)
  AND datepartition >= '2026-03-20-00' AND datepartition <= '2026-03-31-00'
GROUP BY event_type ORDER BY cnt DESC
```
</details>

---

## 5. ATO Timeline: Real Takeover With Late Recovery

Detailed timeline analysis of MID 412977836 (top abuser by DIHE) shows this is **real ATO with late owner recovery** — not account rental. The device-bound challenge solves are recovery behavior, not rental cooperation.

### MID 412977836 Timeline

| Phase | Dates | IPs | Events |
|-------|-------|-----|--------|
| **Abuse** | Mar 20-29 | T-Mobile `2607:fb91:...` `2607:fb90:...` | M2M blocks, no challenges triggered |
| **Owner recovery** | Mar 30 | Comcast `2600:1700:3758:...` | Burst of device-bound challenge solves (iPhone native app), password change via email, ATO super challenge solved |
| **CS self-report** | Mar 31 | — | "mme came for account hacked and want confirm email" — CS restricted account, invalidated sessions, sent password reset |
| **Post-recovery** | Mar 31 - Apr 7 | Comcast `2600:1700:3758:...` | Owner blocks scam accounts; attacker fails login (`LOGIN_FAILURE_WRONG_PASSWORD`) |

The CS restriction note is definitive:
> *"Issue: mme came for account hacked and want confirm email. Action: Restricting the Account || Removed all restrictions as ATO recovery || Invalidated all sessions || Sent password reset link"*

The 12 native device challenge solves all happened on **Mar 30** — triggered by `SETTINGS_CHANGE` as the owner tried to regain control. The abuse phase (Mar 20-29) shows zero challenge solves, zero logins from the owner's IP. This is recovery, not rental.

### What this means for the investigation

The aggregate CS audit signals (step 4) need to be interpreted carefully:
- **Device-bound challenge solves** = owner recovering AFTER abuse, not rental unblocking
- **High ATO challenge solve rates** = owners recovering via email access they still have
- **No self-report in CS audit table** ≠ no self-report. MID 412977836 self-reported via CS chat (captured in restriction notes, not as a separate event_type)
- **Repeated challenge-solve cycles** on other accounts may be multiple recovery attempts or rental — need per-account timeline to distinguish

### MID 951425089 Timeline: Restrict-Recover-Abuse Cycle

MID 951425089 (34 whitelisted attempts) shows a different pattern: **repeated restrict-recover-abuse cycles** with all activity from Pakistan. No geographic split between "attacker" and "owner."

| Phase | Dates | Events |
|-------|-------|--------|
| **Active (PK)** | Mar 1-6 | Logins from two PK ISPs (`154.80`, `119.160`) |
| **Model restricts** | Mar 7 | `SCORER_FAKE_ACCOUNT` (ATO holistic model) + `SCORER_MEMBER_REQUEST` (scraping). Forced logout. |
| **Recovery #1** | Mar 12-13 | Persona ID verification (`NO_ACCESS_TO_PRIMARY_EMAIL` workflow, PK ID card → APPROVED). ATO + email challenges solved from vivo Android phone (PK). Logs in. |
| **Active again** | Mar 15-23 | Logins from PK. Mar 17: `ATTEMPTED_RESTRICTION_BUT_WHITELISTED` (rehab) |
| **Model restricts AGAIN** | Mar 27 | `SCORER_POST_INFERENCE` — "ATO - restrict when decision utility > 0" |
| **Recovery #2** | Mar 31 | Persona ID verification APPEAL (PK ID card → APPROVED, score 0.67 REVIEW_REQUIRED). Restriction cleared, sessions invalidated. |
| **Active + whitelisted** | Apr 1-7 | Challenges solved Apr 1, password changed. Model tries to re-restrict **34 times** (Apr 2-7) — every attempt blocked: "Whitelisted due to recent restriction lift" |

**The critical finding: the restriction-lift whitelist window is being exploited.**

The cycle is: model detects → restricts → account recovers via Persona ID verification → "recent restriction lift" whitelist opens → account resumes the exact behavior that triggered the model → model tries to re-restrict but whitelist blocks it → account operates freely for days.

The model (`SCORER_POST_INFERENCE`) correctly identifies this account as abusive **34 times** in 6 days but cannot act. The whitelist designed to protect recently-recovered legitimate accounts is being weaponized.

**Rental vs ATO remains ambiguous for this account.** All IPs are Pakistan. The Persona ID card is Pakistani. Could be a real owner recovering or a renter using their own ID to unblock. The actionable finding is the same: the whitelist is the defense gap.

<details><summary>Queries</summary>

```sql
-- Full timeline for MID 951425089
SELECT datepartition, event_type, ip_address, notes
FROM u_trustim.event_cs_audit
WHERE memberid = 951425089
  AND datepartition >= '2026-03-01-00' AND datepartition <= '2026-04-07-00'
ORDER BY event_time_seconds

-- Per-account event type summary (top 20 MIDs)
SELECT memberid, event_type, COUNT(*) as cnt
FROM u_trustim.event_cs_audit
WHERE memberid IN (<top 20 MIDs>)
  AND datepartition >= '2026-03-20-00' AND datepartition <= '2026-04-07-00'
  AND (event_type LIKE '%ATO%' OR event_type LIKE '%CHALLENGE%'
    OR event_type LIKE '%PASSWORD%' OR event_type LIKE '%RESTRICTION%'
    OR event_type LIKE '%VERIFICATION%' OR event_type LIKE '%LOGOUT%'
    OR event_type LIKE '%LOGIN%')
GROUP BY memberid, event_type ORDER BY memberid, cnt DESC
```
</details>

---

## 6. Next Steps

- [ ] **Identify L1 cuts**: find what "L1" means in Trust context, then run attribution across all L1 dimensions at scale (not just top 20 accounts)
- [ ] **Whitelisting recommendation**: the "recent restriction lift" whitelist window is the primary defense gap. Models correctly detect abuse but cannot act. Recommend shortening/eliminating the whitelist for accounts with repeat restrict-recover cycles.
- [ ] Timeline MID 1344273667 (29 whitelisted attempts) — confirm same restrict-recover-abuse cycle
- [ ] Quantify: how much DIHE accrues during the whitelist window across the full abuser cohort?
- [ ] Check post-Mar 30 DIHE trend — did the Zambia batch restriction bend the curve?

---

## Appendix

### Tables used
| Table | Purpose |
|-------|---------|
| `u_tdsjobseeker.job_seeker_safety_dash_dihe` | JSS DIHE T7D (levels: JS_Score, JS_Score__Harm_Type, Granular) |
| `u_metrics.account_abuse_harmful_experience_union` | Event-level DIHE with abuser IDs, harm_sub_type, ato_yn |
| `u_trustim.event_cs_audit` | CS audit log (ATO challenges, restrictions, profile changes) |

### Related
- See [investigation-feed-dihe.md](investigation-feed-dihe.md) for the platform-wide Feed DIHE investigation (IOC attribution, abuser profiling)
- [Retina dashboard 31793](https://retina.corp.linkedin.com/retina/dashboards/31793/view?tabId=3) confirms the spike is platform-wide, not JSS-specific
