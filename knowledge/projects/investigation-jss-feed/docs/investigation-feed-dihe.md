# Feed DIHE Investigation (Platform-wide)

**Date:** 2026-04-08 | **Investigator:** Jesus Cortes
**Source table:** `u_metrics.account_abuse_harmful_experience_union` (all members, VIEWED_HOME_FEED_UPDATE)

This investigation covers the platform-wide Feed DIHE increase, discovered during the JSS DIHE investigation. The JSS-specific analysis is in [investigation-jss.md](investigation-jss.md).

---

## 0. The increase

Feed DIHE (Trailing 7d sum of `core_harmful_experience_7d_partial`) shows a clear V-shaped dip and overshoot. Baseline averaged ~19-21M (Feb 22 - Mar 16). After a trough at 15.5M around Mar 22, DIHE recovers sharply to a peak of 23.5M on Mar 31 -- ~20% above baseline. The recovery overshoots pre-trough levels, indicating new harm volume layered on top of the rebound.

This matches the [Retina Scaled DIHE by surfaces chart](https://retina.corp.linkedin.com/retina/beta/charts/333838) (which uses Trailing 7d aggregation on `harmful_experience_7d` from `account_abuse_harmful_experience`).

![Feed DIHE Trailing 7d — VIEWED_HOME_FEED_UPDATE](assets/raw_feed_dihe.png)

Daily granularity (same metric, not rolled up): baseline ~2.5-3.4M, trough 1.78M (Mar 20), peak 4.12M (Mar 30).

![Feed DIHE Daily — VIEWED_HOME_FEED_UPDATE](assets/raw_feed_dihe_daily.png)

<details><summary>Query</summary>

```sql
-- Preamble: SET SESSION li_authorization_user = 'trustim'
-- Step 1: get daily T7D partial values
SELECT datepartition as date_day,
  SUM(core_harmful_experience_7d_partial) as daily_dihe_7d
FROM u_metrics.account_abuse_harmful_experience_union
WHERE harm_type = 'VIEWED_HOME_FEED_UPDATE' AND core_yn = 1
  AND datepartition >= '2026-02-08-00' AND datepartition <= '2026-04-07-00'
GROUP BY datepartition
ORDER BY date_day

-- Step 2: compute trailing 7d rolling sum (SUM of last 7 daily values)
-- This matches the Retina "Trailing 7d harmful_experience_7d" metric
```
</details>

---

## 1. ATO Tier 1 and Tier 2 are driving the increase

Spike analysis (precision/recall feature scan, baseline Mar 9-16 vs spike Mar 23-30) across all 19 categorical columns identified the top IOCs. ATO Tier 1 and Tier 2 together explain the entire increase — Non-ATO and ATO Other Tiers are stable.

- **ATO Tier 1** (red): baseline ~325K/day, peaks at 1.09M on Mar 30 (3.4x). 100% recall, 38.4% precision.
- **ATO Tier 2** (orange): baseline ~470K/day, peaks at 903K on Mar 30 (1.9x). 100% recall, 32.8% precision.

![Feed DIHE: ATO Tier Attribution (Stacked Area)](assets/feed_ato_tier_attribution.png)

<details><summary>Query</summary>

```sql
-- Preamble: SET SESSION li_authorization_user = 'trustim'
SELECT datepartition as date_day,
  CASE
    WHEN ato_yn = 1 AND abuser_trust_tier = 'tier1' THEN 'ATO Tier 1'
    WHEN ato_yn = 1 AND abuser_trust_tier = 'tier2' THEN 'ATO Tier 2'
    WHEN ato_yn = 1 THEN 'ATO Other Tiers'
    ELSE 'Non-ATO'
  END as cohort,
  SUM(core_harmful_experience_7d_partial) as dihe
FROM u_metrics.account_abuse_harmful_experience_union
WHERE harm_type = 'VIEWED_HOME_FEED_UPDATE' AND core_yn = 1
  AND datepartition >= '2026-02-23-00' AND datepartition <= '2026-03-30-00'
GROUP BY datepartition, 2
ORDER BY date_day, cohort
```
</details>

<details><summary>Spike analysis feature scan results (baseline Mar 9-16, spike Mar 23-30)</summary>

| Signal | Baseline % | Spike % | Precision | Recall |
|--------|-----------|---------|-----------|--------|
| `abuser_mlc = FourByFour` | 34.0% | 49.2% | 38.1% | 100% |
| `abuser_trust_tier = tier2` | 27.0% | 36.0% | 32.8% | 100% |
| `abuser_trust_tier = tier1` | 18.9% | 27.5% | 38.4% | 100% |
| `is_abuser_premium = Y` | 7.4% | 15.3% | 56.7% | 84.3% |
| `abuser_payment_status = paying` | 8.7% | 16.2% | 52.1% | 81.9% |
| `ato_yn = 1` | 36.8% | 44.1% | 25.2% | 100% |
| `harm_sub_type = ORIGINAL_IA_POST` | 34.4% | 38.2% | 19.3% | 71.4% |
| `harm_sub_type = VIRAL_ACTION_IA_POST` | 20.0% | 22.0% | 18.7% | 39.8% |
</details>

---

## 2. Within ATO T1/T2: FourByFour Group Posts and Premium are the IOCs

Second spike analysis (within ATO Tier 1+2 only) identifies two overlapping clusters that explain the increase. Baseline (blue), Non-FourByFour (gray), and FourByFour Other (orange) are stable.

- **FourByFour Group Posts** (red): baseline ~140K/day, peaks at 776K on Mar 30 (5.5x). 56% recall, 54% precision.
- **FourByFour Premium non-Group** (purple): baseline ~55K/day, peaks at 318K (5.8x). 53% recall, 65% precision.

These are largely distinct abuser pools (only 139 accounts overlap). The Premium cluster peaked Mar 25-27 then declined, while Group Posts kept climbing through Mar 30, suggesting either different operations or a tactical shift.

![Feed DIHE Full IOC Attribution](assets/feed_full_attribution.png)

<details><summary>Query</summary>

```sql
-- Preamble: SET SESSION li_authorization_user = 'trustim'
SELECT datepartition as date_day,
  CASE
    WHEN ato_yn = 1 AND abuser_trust_tier IN ('tier1','tier2') AND abuser_mlc = 'FourByFour' AND harm_sub_type LIKE '%GROUP%' THEN 'ATO T1/T2: FourByFour Group'
    WHEN ato_yn = 1 AND abuser_trust_tier IN ('tier1','tier2') AND abuser_mlc = 'FourByFour' AND is_abuser_premium = 'Y' THEN 'ATO T1/T2: FourByFour Premium'
    WHEN ato_yn = 1 AND abuser_trust_tier IN ('tier1','tier2') AND abuser_mlc = 'FourByFour' THEN 'ATO T1/T2: FourByFour Other'
    WHEN ato_yn = 1 AND abuser_trust_tier IN ('tier1','tier2') THEN 'ATO T1/T2: Non-FourByFour'
    ELSE 'Baseline (Non-ATO + ATO other)'
  END as cohort,
  SUM(core_harmful_experience_7d_partial) as dihe
FROM u_metrics.account_abuse_harmful_experience_union
WHERE harm_type = 'VIEWED_HOME_FEED_UPDATE' AND core_yn = 1
  AND datepartition >= '2026-02-23-00' AND datepartition <= '2026-03-30-00'
GROUP BY datepartition, 2
ORDER BY date_day, cohort
```
</details>

<details><summary>Spike analysis within ATO T1/T2 (baseline Mar 9-16, spike Mar 23-30)</summary>

| Signal | Baseline % | Spike % | Precision | Recall |
|--------|-----------|---------|-----------|--------|
| `abuser_payment_status = paying` | 17.0% | 31.2% | 64.2% | 58.9% |
| `is_abuser_premium = Y` | 14.9% | 27.8% | 64.6% | 52.7% |
| `harm_sub_type = ORIGINAL_IA_GROUP_POST` | 25.1% | 35.6% | 53.5% | 55.9% |
| `product = GROUP` | 27.8% | 37.7% | 51.3% | 56.7% |
| `abuser_trust_tier = tier1` | 41.0% | 49.2% | 45.0% | 64.9% |
| `abuser_mlc = FourByFour` | 68.9% | 75.2% | 39.6% | 87.4% |
</details>

---

## 3. ATO Vector: Email compromise enables challenge bypass

CS Audit data on the 8,600+ ATO T1/T2 FourByFour abusers reveals the attack chain. All activity spikes 5-10x from baseline (Mar 10-16) to spike period (Mar 23-30).

**Attack chain:**
1. **Credential stuffing** — 12,303 wrong-password events on 2,170 MIDs (5.4x baseline)
2. **Password reset via email** — 2,703 events on 2,019 MIDs (10.8x baseline). Attackers have access to victims' email accounts.
3. **Challenges bypassed** — email-based verification is ineffective because attackers control the email:

| Challenge | Shown MIDs | Solved MIDs | Solve Rate |
|-----------|-----------|-------------|------------|
| ATO Super Challenge | 3,093 | 2,967 | **95.9%** |
| Email PIN | 2,924 | 2,761 | **94.4%** |
| Two-Step Verification | 1,357 | 980 | 72.2% |
| LinkedIn App (native device) | 1,157 | 1,084 | 93.7% |
| LinkedIn App (new device) | 1,535 | 1,045 | 68.1% |

4. **Account modification** — 902 MIDs changed job title, 843 changed photo (building credibility for scam posts)
5. **Restriction whitelist gap** — 4,788 restriction attempts whitelisted on 352 MIDs during spike (3.3x baseline)
6. **Eventual restriction** — 3,334 MIDs restricted during spike (vs 72 during baseline, 46x)

**The population is likely a mix of rental accounts and traditional ATO with email compromise.** The evidence points both ways:

Signals **supporting rental** (owner cooperating):
- **Zero self-reported ATO complaints** — no owner reported compromise
- **0.4% self-recovery rate** — only 13 of 3,334 restricted MIDs completed self-recovery
- **1,084 MIDs solved LinkedIn App challenge on native device** (93.7% solve rate) — requires owner's physical phone
- **457 MIDs still have REMEMBER_ME sessions** active during the abuse period
- **ID verification**: 5,064 MIDs initiated ID verification; 533 APPROVED, 2,747 REVIEW_REQUIRED — real government IDs being submitted

Signals **against pure rental** (traditional ATO indicators):
- **12,303 wrong-password events on 2,170 MIDs** — credential stuffing; rental accounts don't need brute force
- **11.6% native app challenge REJECTION rate** (143 MIDs rejected the push) — some owners are NOT cooperating
- **2,616 session invalidation events on 270 MIDs** (12x baseline) — consistent with hostile password changes, not consensual sharing
- **1,994 MIDs attempted login after restriction** (LOGIN_RESTRICTED_MEMBER_LOGIN) — owners trying to get back into restricted accounts

The credential stuffing signal is hard to reconcile with pure rental — if the owner willingly shares access, the attacker wouldn't need to guess passwords. The 11.6% app rejection rate confirms at least some owners are not cooperating. Most likely this is a **mixed population**: some accounts are rented, some are ATO'd via email compromise, and the attacker uses whatever method works per account.

<details><summary>Query</summary>

```sql
-- Preamble: SET SESSION li_authorization_user = 'trustim'
WITH abusers AS (
  SELECT DISTINCT abuser_id
  FROM u_metrics.account_abuse_harmful_experience_union
  WHERE harm_type = 'VIEWED_HOME_FEED_UPDATE' AND core_yn = 1
    AND ato_yn = 1 AND abuser_trust_tier IN ('tier1','tier2')
    AND abuser_mlc = 'FourByFour'
    AND datepartition >= '2026-03-23-00' AND datepartition <= '2026-03-30-00'
)
SELECT cs.cs_event_type,
  CASE
    WHEN cs.datepartition < '2026-03-17-00' THEN 'Baseline (Mar 10-16)'
    WHEN cs.datepartition < '2026-03-23-00' THEN 'Ramp (Mar 17-22)'
    ELSE 'Spike (Mar 23-30)'
  END as period,
  COUNT(*) as events, COUNT(DISTINCT cs.memberid) as mids
FROM u_trustim.event_cs_audit cs
INNER JOIN abusers a ON cs.memberid = a.abuser_id
WHERE cs.datepartition >= '2026-03-10-00' AND cs.datepartition <= '2026-03-30-00'
GROUP BY 1, 2 ORDER BY 1, 2
```
</details>

---

## 4. Next: L1 Analysis (Standard Trust Attribution Cuts)

Per the [48-hour L1 proposal](https://docs.google.com/document/d/1Xn4e8qEq6vjXzRb8wyq0p6ijz3vNNe5ZL-ynrbZcVBo), L1 = standard dimensional cuts to characterize abuse. The goal: *"The movement is driven by [cohort] with [characteristics], doing [activities], affecting [victims]. Our defenses [performed as follows]."*

### L1 dimensions — coverage status

**Abuser-side:**
| Dimension | Column | Status |
|-----------|--------|--------|
| ATO vs FA | `ato_yn` | Done (Step 1) — ATO drives 100% |
| Authenticity tier | `abuser_trust_tier` | Done (Step 1) — Tier 1+2 |
| MLC | `abuser_mlc` | Done (Step 2) — FourByFour |
| Premium status | `is_abuser_premium` | Done (Step 2) — 65% precision |
| Paid status | `abuser_payment_status` | Done (Step 1 scan) |
| LSS/LMS/LLS/Recruiter | `is_abuser_lss` etc. | Done (scan) — not a signal |
| Account age | `abuser_reg_date_partition` | **TODO** — need to bucket |
| NDA category | not in source table | **TODO** — need join |
| Verification category | not in source table | **TODO** — need join |
| Rental signup country | not in source table | **TODO** — need join |
| Restriction history | not in source table | **TODO** — need join with `data_derived.member_restrictions` |
| Real vs Fake | `real_yn` | Done (scan) — `NULL` (= ATO, no signal) |

**Victim-side:**
| Dimension | Column | Status |
|-----------|--------|--------|
| JSS status | `victim_jss_status_grouped` | Done (scan) — evenly distributed, not a signal |
| Victim MLC | `victim_mlc` | Done (scan) — not a signal |
| Verification | not in source table | **TODO** |
| New member | derivable from victim data | **TODO** |

**Interaction:**
| Dimension | Column | Status |
|-----------|--------|--------|
| Surface | `harm_type` / `surface` | Done — VIEWED_HOME_FEED_UPDATE only |
| Harm sub-type | `harm_sub_type` | Done (Step 2) — Group Posts + Original IA Post |
| Product | `product` | Done (Step 2) — GROUP |
| Connected/unconnected | `unconnected_yn` | Done (scan) — mostly unconnected (86%), not differential |

### Remaining L1 work
- [ ] Account age bucketing (`abuser_reg_date_partition`)
- [ ] NDA, verification, rental signup country — need to identify joinable tables
- [ ] Restriction history — join with `data_derived.member_restrictions`
- [ ] Defense performance: were these accounts caught by models or manual review?
- [ ] Content analysis (tracking.UgcPostV2Event)
- [ ] Rental vs ATO segmentation: need concurrent geo sessions or post-restriction support contacts

---

## Appendix

### CS Audit Log signals (from u_trustim.event_cs_audit)

| Event | Count | MIDs | Note |
|-------|-------|------|------|
| SHOWN_ATO_SUPER_CHALLENGE | 1,800 | 241 | Accounts flagged as ATO |
| SOLVED_ATO_SUPER_CHALLENGE | 1,364 | 236 | 98% solve rate -- rental or email access |
| ATTEMPTED_RESTRICTION_BUT_WHITELISTED | 738 | 41 | Defense gap |
| LOGIN_FAILURE_WRONG_PASSWORD (Nigeria) | 322 | 53 | Credential stuffing signal |
| PROFILE_JOB_CHANGED | 511 | 128 | Account modification post-ATO |
| PROFILE_PHOTO_CHANGED | 262 | 115 | Account modification post-ATO |

### Abuser profile (top 20 accounts)

- Mostly FourByFour MLC, 8/30 Premium, all `reg_date = null` (confirmed ATO)
- Login IPs: distributed (Brazil 32 MIDs, USA 96, Nigeria 110, India 48). No single country isolates the spike.
- Login methods: credentials (27 MIDs), Google 3P (12), password reset (9)
- Detection gap: 9/11 restricted accounts caught manually (CSTOOL_REP), not models.

### Tables used
| Table | Purpose |
|-------|---------|
| `u_metrics.account_abuse_harmful_experience_union` | Event-level DIHE with harm_sub_type, ato_yn, abuser/victim IDs (source table behind `u_trustim.flatten_harmful_experiences` view) |
| `u_trustim.event_cs_audit` | CS audit log (ATO challenges, restrictions, profile changes) |
| `data_derived.member_restrictions` | Restriction records |
| `tracking.loginevent` | Login events (method, IP, UA) |
