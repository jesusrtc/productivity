# SEV Calculator Backtesting: DIHE Incident Investigation

**Author:** jcortes
**Date:** 2026-04-08
**Status:** In Progress

---

## Objective

Backtest the SEV calculator's DIHE widget against real incidents from InResponse (Nov 1 2025 -- Mar 15 2026) to validate severity scoring accuracy. We will compare the DIHE impact measured by the widget against the actual severity assigned during incident response.

**Scope:** ATO, abuse-driven harm, and DIHE elevation incidents only -- no scraping, no registration.

---

## Data Source

- **DIHE metric table:** `u_tds.fact_experience_base`
  - Coverage: daily partitions from 2025-10-01 onward
  - Volume: ~3.5B--5.3B rows/day (weekday), ~3.1B--3.9B (weekend)
  - Holiday dips observed (Dec 22 -- Jan 4)

- **Incident source:** InResponse (airp-web) via `ir` CLI
  - 221 total incidents in date range
  - 37 DIHE-relevant after filtering out scraping/registration

---

## Incidents Under Investigation

### ATO / Account Compromise (11 incidents)

Direct account takeover activity causing downstream member harm.

| IR ID | Severity | Date | Title |
|---|---|---|---|
| 260333608 | SEV5 | 2026-03-13 | Sales Nav ATO Abuse |
| 260339929 | SEV2 | 2026-03-04 | Alert for ATO Self Reports Non-Gamified |
| 260339094 | SEV2 | 2026-03-04 | ATO member report sev 2 |
| 260336223 | P1 | 2026-03-04 | BD Fake/ATO Accounts for Sale in FB Groups |
| 260298462 | None | 2026-02-10 | Password Reset Spike |
| 260151453 | Minor | 2026-01-13 | Alert for ATO Self Reports Non-Gamified |
| 251224980 | Minor | 2025-12-02 | Alert for ATO Self Reports Non-Gamified |
| 251120144 | P1 | 2025-11-28 | CT-126 - Rental Accounts with Identical Titles |
| 251136699 | None | 2025-11-25 | ATO/rental track |
| 251154703 | P1 | 2025-11-05 | RentHub - Account Rental Prep |
| 251162908 | None | 2025-11-04 | Members Logging into other members accounts via remember me |

### DIHE / Harm Metric Elevations (6 incidents)

Direct DIHE signal elevations detected by alerting or manual observation.

| IR ID | Severity | Date | Title |
|---|---|---|---|
| 260297696 | None | 2026-02-10 | Elevation in Hiring Intent Feed DIHE |
| 260195947 | Minor | 2026-01-21 | FA DIHE up based on WoW or Wo3W or threshold |
| 251226740 | None | 2025-12-22 | Home Feed DIHE Incident |
| 251257289 | Minor | 2025-12-03 | Elevation in Total DIHE/1K for job seekers (JSS) |
| 251183658 | Medium | 2025-11-25 | Semaphore and Self Reports Spike |
| 260154279 | SEV1 | 2026-01-13 | Abusive accounts using RFS for fake hiring messaging |

### Spam / Abuse / Phishing (3 incidents)

Abuse patterns with potential DIHE impact on messaging and feed.

| IR ID | Severity | Date | Title |
|---|---|---|---|
| 260147807 | P2 | 2026-01-12 | Sales Navigator/Premium subscription abuse by fake accounts |
| 251293624 | None | 2025-12-15 | Ads incident needing rule |
| 251117960 | None | 2025-11-14 | Elevated abuse from Cambodian IP |

### State-Sponsored / Threat Actor (2 incidents)

| IR ID | Severity | Date | Title |
|---|---|---|---|
| 251154966 | None | 2025-11-04 | Iran and North Korea State Sponsored ATOs and Account Rentals |
| 251187830 | Confirmed Attack | 2025-11-03 | DPRK Threat Actor Activity |

---

## Methodology

1. For each incident, identify the incident date range (started_at to mitigated_at)
2. Query `u_tds.fact_experience_base` for the DIHE sub-categories (invites/messages, feed posts, feed comments) during that window
3. Compute WoW T7D comparisons using the SEV calculator's baseline gates
4. Compare the SEV calculator's computed severity (SEV 1-4) against the actual severity assigned in InResponse
5. Identify gaps: incidents where the calculator would over-score, under-score, or miss entirely

---

## Success Criteria

- SEV calculator severity matches actual incident severity within 1 level for >= 80% of incidents
- No SEV1/SEV2 incidents are missed (scored as SEV4 or no-SEV)
- False positive rate (calculator flags SEV when incident was false positive) < 20%

---

## Next Steps

- [ ] Pull full incident details (summary, timeline, mitigation) for all 22 incidents via `ir incident view`
- [ ] Query DIHE metrics from `fact_experience_base` aligned to each incident window
- [ ] Run SEV calculator widget against each incident's data
- [ ] Build comparison matrix: calculated SEV vs actual SEV
- [ ] Document findings and recommend calibration adjustments
