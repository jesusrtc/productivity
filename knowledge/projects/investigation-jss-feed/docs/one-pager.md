# Feed DIHE Spike: Investigation One-Pager

**Status:** Active | **Date:** April 9, 2026 | **Investigator:** Jesus Cortes
**Oncall IM:** Jesus Talamantes | **DRI:** Gina Hernandez

---

## What happened

Feed DIHE (VIEWED_HOME_FEED_UPDATE) spiked ~20% above baseline, peaking at 23.5M trailing 7d on Mar 31. The increase was first detected through the JSS DIHE metric (+26.2% WoW, Mar 22→29) and confirmed as platform-wide — not JSS-specific. DS validated the data is real, not a pipeline artifact.

![Feed DIHE Trailing 7d](assets/raw_feed_dihe.png)

![Feed DIHE Daily](assets/raw_feed_dihe_daily.png)

---

## Who is driving it

Spike analysis (precision/recall scan across 19 columns, baseline Mar 9-16 vs spike Mar 23-30) narrows the increase through three levels:

**Level 1 — ATO Tier 1 and Tier 2 explain the entire increase.** Non-ATO and other ATO tiers are flat. ATO Tier 1 went from 325K/day baseline to 1.09M peak (3.4x). ATO Tier 2 went from 470K/day to 903K (1.9x).

![ATO Tier Attribution](assets/feed_ato_tier_attribution.png)

**Level 2 — Within ATO T1/T2, FourByFour MLC accounts are responsible.** FourByFour explains 87% of the T1/T2 increase. Two clusters emerge:

| Cluster | Baseline | Peak (Mar 30) | Multiplier | Precision | Recall |
|---------|----------|---------------|------------|-----------|--------|
| FourByFour + Group Posts | 140K/day | 776K | 5.5x | 54% | 56% |
| FourByFour + Premium (non-Group) | 55K/day | 318K | 5.8x | 65% | 53% |

These are largely distinct abuser pools (only 139 accounts overlap out of ~8,600). The Premium cluster peaked Mar 25-27 then declined; Group Posts kept climbing through Mar 30.

![Full IOC Attribution](assets/feed_full_attribution.png)

---

## CS Audit: What happened on these 7,596 accounts (Mar 23-30)

All numbers below use the same denominator: **7,596 ATO T1/T2 FourByFour accounts** from the DIHE table during the spike window. CS audit events are from the same date range.

- **7,596 accounts** — ATO Tier 1+2, FourByFour MLC, 7.2M DIHE
  - **3,480 (45.8%)** logged in during this window
  - **2,164 (28.5%)** had wrong-password failures
  - **2,012 (26.5%)** changed password via email link
  - **Challenges shown and solved:**
    - ATO Super Challenge: **3,082 shown → 2,954 solved (95.8%)**
    - Email PIN: **2,910 shown → 2,748 solved (94.4%)**
    - Two-Step Verification: **1,359 shown → 980 solved (72.1%)**
    - LinkedIn App native device: **1,147 shown → 1,074 solved (93.6%)**, 141 rejected (12.3%)
    - LinkedIn App new device: **1,523 shown → 1,035 solved (67.9%)**, 82 rejected (5.4%)
  - **Profile modification:** 908 changed headline, 903 changed job, 843 changed photo
  - **3,320 (43.7%) restricted** during the spike
    - 1,984 (59.8% of restricted) attempted login after restriction
    - 452 (13.6% of restricted) had restriction cleared
    - 353 accounts had **4,790 whitelist blocks** — model tried to re-restrict but was blocked
    - 13 (0.4% of restricted) completed self-recovery
  - **1,946 (25.6%)** initiated ID verification
    - 1,170 received scoring response
  - **457 (6.0%)** had active REMEMBER_ME sessions (owner's device still logged in)

**Challenge solve rates by type** — the gradient reveals the access mechanism:

| Challenge | Solve Rate | Requires |
|-----------|-----------|----------|
| ATO Super Challenge | 95.8% | Email access |
| Email PIN | 94.4% | Email access |
| LinkedIn App (native device) | 93.6% | Owner's physical phone |
| Two-Step Verification | 72.1% | Authenticator or SMS |
| LinkedIn App (new device) | 67.9% | Owner approves from existing device |

Email-based challenges are solved at 94-96%. The native device app challenge — which requires the owner's physical phone — is solved at 93.6% (1,074 of 1,147 accounts), but 141 accounts (12.3%) actively rejected it.

**What this means:** The operator has email access on nearly all accounts. On 1,074 accounts, the owner's physical phone was used to approve a challenge. On 141 accounts, the owner refused. On 13 of 3,320 restricted accounts, the owner completed self-recovery. Per-account timelines show both patterns: MID 412977836 is a clear hostile takeover (owner contacts CS: *"account hacked, want to confirm email"*); MID 951425089 shows restrict-recover-abuse cycles with the same Pakistani ID used for recovery, no geographic split between operator and owner.

---

## Defense gaps

**1. Restriction whitelist exploitation.** After an account recovers from restriction via ID verification, a "recent restriction lift" whitelist window opens. During this window, models correctly identify abuse but cannot re-restrict. MID 951425089: the model flagged the account **34 times in 6 days** — every attempt blocked by the whitelist. 4,788 restriction attempts were whitelisted across 352 MIDs during the spike (3.3x baseline).

**2. Email-based challenges are ineffective.** When the operator has email access (whether through compromise or the owner sharing it), ATO Super Challenge and Email PIN are solved at 94-96%. These challenges do not stop this attack vector.

**3. Late detection, manual enforcement.** A batch of 307 ATO accounts linked to Zambia fake ad campaigns was only restricted on Mar 30 via manual CS action ("JSS-Zambia-ATO-coadmin-pwdreset") — the last day of the spike window. All Feed DIHE from these accounts accrued unmitigated until then.

---

## Overlap with Ads SEV 3

The restriction notes on multiple abuser accounts reference the ongoing Ads SEV 3: *"ATO remediation for 307 compromised accounts used as BZM co-admins on Zambia fake ad accounts."* The Ads SEV and this Feed incident share ATO supply — compromised FourByFour accounts used across both attack surfaces (Ads + Group Posts).

| Dimension | Ads SEV 3 | Feed DIHE (This Incident) |
|-----------|-----------|--------------------------|
| Attack surface | LinkedIn Ads / Campaign Manager | LinkedIn Groups (feed posts) |
| Primary harm_type | VIEWED_AD | VIEWED_HOME_FEED_UPDATE |
| Abuser profile | ATO FourByFour, some Premium | ATO T1/T2 FourByFour, some Premium |
| Scale | 705 MIDs, 46K+ ad creatives | 7,596 MIDs, Group spam |
| Scam content | Crypto/financial investment ads | Fake hiring/recruitment posts |

---

## Key metrics

| Metric | Value |
|--------|-------|
| Peak Feed DIHE (trailing 7d) | 23.5M (Mar 31) — 20% above baseline |
| Peak Feed DIHE (daily) | 4.12M (Mar 30) — 47% above baseline |
| Abuser accounts (ATO T1/T2 FourByFour) | 7,596 |
| Total DIHE from these accounts (spike window) | 7.2M |
| Restricted during spike | 3,320 / 7,596 (43.7%) |
| ATO Super Challenge solve rate | 2,954 / 3,082 (95.8%) |
| Native device app challenge solved | 1,074 / 1,147 (93.6%) |
| Native device app challenge rejected | 141 / 1,147 (12.3%) |
| Self-recovery after restriction | 13 / 3,320 (0.4%) |
| Restriction whitelist blocks | 4,790 events on 353 accounts |
| Password changed via email | 2,012 / 7,596 (26.5%) |

---

## Next steps

- Complete L1 analysis: account age bucketing, NDA category, verification status, restriction history
- Content analysis: characterize what these accounts are posting (tracking.UgcPostV2Event)
- Quantify DIHE accrued during restriction whitelist windows
- Geographic profiling: login locations during abuse vs owner historical location
- Assess whether the restriction whitelist window can be shortened or removed for accounts with repeat restrict-recover cycles

---

## Datasets

| Table | Purpose |
|-------|---------|
| `u_metrics.account_abuse_harmful_experience_union` | Source table for Feed DIHE (behind `u_trustim.flatten_harmful_experiences` view) |
| `u_tdsjobseeker.job_seeker_safety_dash_dihe` | JSS-specific DIHE (how the spike was first detected) |
| `u_trustim.event_cs_audit` | CS audit log: challenges, restrictions, logins, profile changes |

## References

- [Retina: Scaled DIHE by surfaces](https://retina.corp.linkedin.com/retina/beta/charts/333838)
- [Retina: JSS DIHE dashboard](https://retina.corp.linkedin.com/retina/dashboards/31793/view?tabId=3)
- [48-hour L1 analysis proposal](https://docs.google.com/document/d/1Xn4e8qEq6vjXzRb8wyq0p6ijz3vNNe5ZL-ynrbZcVBo)
- [Ads SEV 3 Incident Doc](https://docs.google.com/document/d/1NiPI35Eu6aLSyUnBelrQC8KqqRfndGWuku4aJKmlYOI/edit)
- [JSS Feed Triage (Sam's analysis)](https://docs.google.com/document/d/1VJu0rMWhItzH3LLrRiKjp2t8OumipafcF530IO-J-uc/edit)

---

## Update 2026-04-09: IP / Session Analysis and Notable Accounts

### IP mismatch between login and Email PIN challenge solve

Of the 2,748 accounts that solved the Email PIN challenge during the spike, we checked whether the solve IP ever appeared in the account's login IPs (same window):

- **903 accounts (32.9%)**: all Email PIN solves from IPs also seen in logins — same person/location
- **1,228 accounts (44.7%)**: Email PIN solves from IPs NEVER seen in logins — different location
- **617 accounts (22.4%)**: mixed — some solves match login IPs, some don't

44.7% of accounts solved Email PIN from an IP that never appeared in their login history. The challenge was solved from a different network than where the account was being operated.

### ID Verification: new browser on every account

ID Verification scoring responses show `browserIdHistoryMatch=false` on **every single account** — all 1,170 scored accounts were on a new browser. A subset also had `profileCountryMatch=false`:

| IP Country | Profile Mismatch | MIDs |
|-----------|-----------------|------|
| Pakistan | Yes | 18 |
| Egypt | Yes | 16 |
| United States | Yes | 14 |
| India | Yes | 13 |

These accounts were operating from a country that does not match their LinkedIn profile country.

### Notable accounts

| MID | DIHE | Pattern | Link |
|-----|------|---------|------|
| 582270992 | — | **29 email PIN solves from 28 different IPs**, 46 logins from 36 IPs / 43 browsers, 29 password resets from 28 IPs. Massive IP rotation — either shared across dozens of operators or cycling through proxies. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/582270992/activity) |
| 1557240416 | — | 62 wrong-password failures from 26 IPs, 42 logins from 24 IPs, 16 native app solves, **5 whitelist blocks**, restricted twice. Heavy brute force + owner solving native device challenges. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/1557240416/activity) |
| 1003465280 | — | 61 logins from 33 IPs / 53 browsers, 3 native app solves, 8 wrong password failures each from a different IP. Account accessed from many locations. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/1003465280/activity) |
| 412977836 | 1.0M | Top abuser by DIHE. Tier 1, Premium. Confirmed hostile ATO: owner recovered Mar 30, contacted CS Mar 31 (*"account hacked"*). 12 native device app solves = recovery, not rental. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/412977836/activity) |
| 426298907 | 545K | Tier 2, Premium. Linked to Zambia Ads SEV (*"ATO remediation for 307 compromised accounts"*). 24 logins from 9 IPs, 11 email PIN solves from 2 IPs. Restricted via manual batch Mar 30. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/426298907/activity) |
| 951425089 | — | Restrict-recover-abuse cycle. All activity from Pakistan. Model flagged 34 times in 6 days, every re-restriction blocked by whitelist. Pakistani ID card used for recovery. | [CS Audit](https://cstool.www.linkedin.com/trust-tool/member/951425089/activity) |

### Reincidence: restrict-recover-abuse cycles

From the 7,596 accounts, checking restriction + whitelist events across Mar 1 - Apr 7:

| Pattern | MIDs | Restrictions | Whitelist Blocks |
|---------|------|-------------|-----------------|
| Restricted once only | 5,935 | 5,935 | 0 |
| Restricted once + whitelist blocks | 744 | 744 | 7,683 |
| Re-restricted (2+ times) | 573 | 1,202 | 0 |
| Re-restricted + whitelist blocks | 280 | 616 | 7,494 |

**1,024 accounts (13.6%)** had whitelist blocks — the model tried to re-restrict but was blocked by the "recent restriction lift" whitelist. These 1,024 accounts generated **15,177 whitelist block events** total. The 280 worst accounts averaged 26.8 whitelist blocks each.

**853 accounts (11.3%)** were re-restricted 2+ times — the restrict-recover-abuse cycle repeated.

### Restriction notes: what models are catching and what they say

The `notes` field on restriction events reveals both automated model detections and manual batch actions:

**Automated model detections:**

| Model / Rule | MIDs | What it catches |
|-------------|------|----------------|
| MONEY_SCAM_IDENTITY (content) | 1,712 | Content model flagging scam posts |
| SCORER_FAKE_ACCOUNT (ATO holistic xgboost) | 331 | ATO detection model |
| SCORER_MEMBER_REQUEST (scraping) | 302 | These accounts also scrape profiles |
| Ghostlock ATO (account management) | 236 | *"restrict if handle removal after successful PWR reset from country mismatch"* |
| SCORER_POST_INFERENCE (content ATO) | 124 | *"restrict when decision utility > 0"* |

**Manual batch actions (CS tooling):**

| Batch | MIDs | Date | Notes |
|-------|------|------|-------|
| CT-127 ATO Group/Feed Posters | 101 | Apr 3 | *"ATO Accounts posting fraudulent group/feed content for fake jobs. ATO'd by NG IP. Due diligence required if member appeals with valid id. Do not lift as false positive, full ATO recovery is needed because bad actors have enabled remember me."* |
| Linkedbooster_April PWI | 63 | Apr 3 | *"Linkedbooster_April PWI + Kill session"* — Linkedbooster is a known commercial ATO/automation tool |

**Key facts from the notes:**
- The content model (MONEY_SCAM_IDENTITY) is the largest single detector at 1,712 MIDs — it catches the scam posts
- Ghostlock ATO detects "PWR reset from country mismatch" — the password-reset-from-different-country signal
- The CT-127 batch explicitly says "ATO'd by NG IP" (Nigeria) and warns "bad actors have enabled remember me" — meaning attackers persist sessions to avoid re-authentication
- Linkedbooster is a known ATO-as-a-service tool, confirming commercial ATO infrastructure involvement
- Models correctly detect these accounts but the whitelist blocks re-restriction on 1,024 of them

### Key takeaway

MID 582270992 is the most extreme example: 29 password resets and 29 email PIN solves, almost each from a unique IP. This is not one attacker with email access — it's either an account being shared across an operator network, or automated credential cycling at scale. The 44.7% IP mismatch rate across the full population suggests this pattern extends well beyond a single account.

The restriction notes confirm the attack is recognized: content models catch the scam posts, ATO models flag the compromised accounts, and CS has run manual batches. The gap is not detection — it's the whitelist window that allows 1,024 accounts to resume after recovery, despite models correctly flagging them again.
