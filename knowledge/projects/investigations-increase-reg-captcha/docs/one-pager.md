# Investigation Report: Registration Signup Drop — Apr 7 2026

**Investigator:** jcortes (IM team)
**Date:** 2026-04-07
**Status:** In Progress

---

## Summary

On 2026-04-07, registration signups dropped WoW after the reactive registration model was re-deployed for the first time since Mar 9. The model was reverted at 7:30pm PT while IM investigates. Over the past 4-5 weeks, signups were inflated due to the paused reactive model allowing attacks through.

**Finding:** The inflated signups are confirmed abuse. 30-43% of all registration scoring events over Apr 5-7 are flagged HIGHLY_ABUSIVE by the autoretrained model. The dominant attack is a fake account campaign using residential proxies (Comcast US), Chrome/Windows 10, and custom vanity email domains (`firstname+lastname.tld` pattern) across 157-188K unique domains per day. Of accounts registered on Apr 5, 43.6% (318K of 730K) were restricted within 1-2 days. The reactive model deployment on Apr 7 was correctly catching this abuse — registrations dropped from ~50K/hr pre-deployment to ~19-22K/hr post-deployment, consistent with blocking the attack traffic.

**Recommendation:** Re-ramp of the reactive model is safe and recommended. The model is correctly identifying abuse. The WoW signup drop on Apr 7 was the model removing fake account traffic that had been inflating numbers for 4 weeks. The "normal" baseline is the lower number, not the inflated one.

---

## Background

The reactive registration model is an auto-retrained weekly model focused on catching latest attacks missed by Auryn. On Mar 9, auto-deploy was paused due to resiliency issues. No deployments for ~4 weeks. On Apr 7, a new version was deployed, causing a WoW signup drop. The model was reverted at 7:30pm while IM validates.

### Timeline

| Time (PT)          | Event                                                        |
|--------------------|--------------------------------------------------------------|
| Mar 9              | Reactive reg model auto-deploy paused (resiliency issue)     |
| Mar 9 — Apr 6      | ~4 weeks with no reactive model updates; signups inflate     |
| Apr 7, 9:45am      | New reactive model deploys to lor1                           |
| Apr 7, 11:15am     | Model deploys to lva1                                        |
| Apr 7, 12:30pm     | Model deploys to ltx1                                        |
| Apr 7, ~5:50pm     | Separate registration attack begins                          |
| Apr 7, 7:30pm      | Model reverted                                               |

---

## Investigation

### 1. Abuse Volume in Registration Scoring (Apr 5-7)

Queried `tracking_hourly.scoreeventforregistration` for the activated rules across 3 days:

| Day | Total Score Events | HIGHLY_ABUSIVE | % Abusive | Unique Custom Email Domains |
|-----|-------------------|----------------|-----------|---------------------------|
| Apr 5 | 6.28M | 2.68M | **42.7%** | 157K |
| Apr 6 | 6.32M | 2.29M | **36.2%** | 188K |
| Apr 7 | 6.54M | 1.98M | **30.3%** | 176K |

The `Give evercaptcha if any version of the autoretrained fake_unprevented registration models classifies as HIGHLY_ABUSIVE` rule is the dominant signal, firing 2-2.7M times/day. Other elevated rules:

| Rule | Apr 5 | Apr 6 | Apr 7 |
|------|-------|-------|-------|
| HIGHLY_ABUSIVE (autoretrained) | 2.68M | 2.29M | 1.98M |
| PHONE_CHALLENGE (laser RegistrationModel) | 1.50M | 2.11M | 2.03M |
| EVERCAPTCHA (quasar v16_2) | 1.10M | 782K | 996K |
| EVERCAPTCHA (laser RegistrationModel) | 1.03M | 356K | 453K |

### 2. IOC Attribution — Fake Account Campaign

The HIGHLY_ABUSIVE cohort on Comcast US (the largest single IP org) shows a clear attack pattern:

**Profile:**
- **IP Org:** Comcast Cable (residential proxy) — 1.17M events on Apr 7 alone, 61% flagged HIGHLY_ABUSIVE
- **Browser/OS:** Chrome on Windows 10.0 — uniform fingerprint across all events
- **Registration type:** COLD
- **Email domains:** Custom vanity domains following `firstname+lastname.tld` pattern:
  - `christopherlam.company`, `lisabell.design`, `carolynbrock.tech`, `davidhall.labs`, `lisapark.digital`, `michaelbridges.creative`, `kristenray.studio`, `richarddavis.tech`, etc.
  - 500-700+ registrations per domain per day

**Top abusive email domains globally (Apr 7):**

| Email Domain | Total Events | HIGHLY_ABUSIVE | % Abusive |
|-------------|-------------|----------------|-----------|
| gmx.com | 65,389 | 45,005 | 69% |
| inlook.cloud (typosquat) | 8,672 | 3,424 | 39% |
| hotmeil.net (typosquat) | 4,531 | 1,615 | 36% |
| deltajohnsons.com | 4,113 | 2,785 | 68% |
| firstname+lastname.tld pattern | ~4-5K each | ~700-1K each | ~20% |

### 3. Registration Volume and Model Impact

**Daily registrations (Apr 5-7):**

| Day | Registrations | Notes |
|-----|--------------|-------|
| Apr 5 | 729,830 | Normal attack volume (model paused) |
| Apr 6 | 885,556 | Higher — Sunday attack volume |
| Apr 7 | 762,525 | Drop after model deployed mid-morning |

**Hourly breakdown on Apr 7** shows the model's impact clearly:
- Pre-deployment (midnight-9am): 36-50K regs/hr (inflated with attack traffic)
- Post-deployment (10am-5pm): dropped to 19-27K regs/hr
- Post-revert (7:30pm+): recovering toward inflated levels

### 4. Restriction Rate Confirms Abuse

Of 729,830 accounts registered on Apr 5, **318,546 (43.6%) were restricted** (spam or login restriction) within 1-2 days via `tracking.UserAccountRestrictionEvent`. Restriction data for Apr 7 has not landed yet (1-day lag).

Restriction types on Apr 5-6 across all accounts:
- SET_SPAM_RESTRICTION: 793K unique members
- SET_LOGIN_RESTRICTION: 796K unique members
- SET_LOGIN_RESTRICTION + CLOSE_ACCOUNT: 94K unique members
- SET_SPAM_RESTRICTION + accountlabel=FAKE: 19.5K unique members explicitly labeled FAKE

### 5. Grafana Observations

**EVERCAPTCHA Attempts** spiked from ~5 QPS baseline to ~40 QPS around Apr 3-5 (mean 14.1 vs 1-week overlay 5.1). This is consistent with the HIGHLY_ABUSIVE rule firing elevated across 626+ hosts.

**Registration attempts** elevated starting ~Apr 2 with cold signup success rate dropping from ~38% to ~25-30%.

**NOC Growth signups WoW** showed clear downward trend across all fabrics starting ~9:30am on Apr 7, tracking the staggered model rollout.

---

## Conclusion

The signup drop on Apr 7 is **not a false positive**. The reactive model is correctly identifying and blocking a large-scale fake account campaign that has been inflating registration numbers for ~4 weeks while the model was paused. Key evidence:

1. **30-43% of all scoring events** are flagged HIGHLY_ABUSIVE
2. **Clear attack signature**: residential proxies (Comcast), Chrome/Win10, custom `firstname+lastname.tld` email domains, 157-188K unique domains/day
3. **43.6% restriction rate** on accounts created during the attack period
4. **Hourly registration drop** directly correlates with model deployment across fabrics

The "normal" baseline is the post-model numbers (~19-27K/hr), not the inflated pre-model numbers (~36-50K/hr). Comparing against last week's inflated numbers creates a false WoW gap.

## Next Steps

- [x] Confirm attack triggers — HIGHLY_ABUSIVE rule + residential proxy fake account campaign
- [x] Validate reactive model catches are abuse, not false positives
- [ ] Cross-reference with scraping table (`u_metrics.scraping_member_data_egress_union`) once data catches up — confirm scraping overlap
- [ ] Recommend re-ramp of reactive model to Dinesh's team
- [ ] Monitor post-ramp metrics to ensure no false positive impact on legitimate signups

## Stakeholders

Prachi Agarwal, Jia Wang, Dinesh Rengasamy Thirumeni Palanivelu, Zihua Liu, Avinash Konda, Animesh Ramesh
