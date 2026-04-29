---
title: "SEV Calculator Refinement & Rollout Strategy"
date: 2026-04-02
type: meeting
scope: org
projects: [davi]
tags: [sev-calculator, rollout, back-testing, scraping, soft-launch]
people: [hezus]
---

# SEV Calculator Refinement & Rollout Strategy

## TL;DR

The meeting focuses on the refinement and rollout strategy for the SEV Calculator, a tool designed to help the team quantify the impact of abuse patterns (such as messaging or invitation spikes) that do not trigger top-line metric thresholds. The core discussion revolves around establishing confidence in the tool's thresholds through back-testing past incidents, defining what constitutes a "cohort" (e.g., user agents vs. specific message patterns), and determining the appropriate internal workflow for declaring a Site Emergency (SEV) based on the calculator's output. The team aims for a "soft launch" where the tool serves as a guidance mechanism for the IM and SI teams rather than an automated trigger.

## Notes

- The SEV calculator provides time-series information on projected DIHE (Daily Impacted Hostile Entities) and data egress for a set of member IDs.
- Data egress scraping thresholds were previously disabled during a refactor but can be re-enabled if necessary.
- The tool is currently available as a widget for anyone with a list of member IDs and an optional date.
- The team needs to decide how to roll the tool out and how users should interpret the output.
- There is a lack of confidence in the current thresholds because they have not yet been validated against past incidents.
- The team suggests a soft launch where the IM or Agility teams use the calculator and share results in the Agility SEV classification channel for alignment.
- The calculator assumes a "worst-case" scenario by treating all input accounts as bad actors to determine their footprint.
- The tool helps address "small-ish" cohorts that are not top-line spikes but are definitely abusive.
- The current vanilla implementation of the calculator is time-agnostic and relies on the user to provide a specific cohort of IDs.
- Hezus is working on logic to help "back out" from specific accounts to identify a broader pattern or cohort over a time range.
- A SEV is triggered if the trajectory of the abuse is steep enough and meets a minimum size criterion.
- The trajectory requirement was specifically included to avoid triggering SEVs for stable, non-increasing patterns like "ducktail".
- The calculator normalizes different types of abuse into a common "currency" of harm or data egress.
- The definition of a "cohort" is a point of concern, as segmenting a spike into too many specific patterns (like user agents) might prevent any single group from hitting the SEV threshold.
- The team discusses using broader indicators, like "moving off-platform to a financial site," to define larger, more impactful cohorts.
- Back-testing is required for several incident types, including free trial abuse and RPS (Request for Service) spikes.
- The team notes that the timing of the calculation matters because the current criteria rely on "velocity" or the rate of ramping up.
- Stable but large abuse patterns (e.g., 20% of DIHE) might be better handled via product roadmaps rather than the SEV framework.
- The scraping team measures data egress for "new accounts," which is a much broader cohort than specific comment patterns.
- The team identifies several past cases for back-testing: account rentals, IDV bugs, and open profile abuse on LTS.
- The percentage of scraping data egress showed a spike in September 2025 but remained below the February 2026 baseline.
- New variations of scraping metrics (extracting extension scrapers or tracking profile headlines) show much more significant upticks than the current top-line metric.
- The IM and SI teams will be the primary users of the calculator during the initial phase.

## Action Items

- [ ] Hezus: Back-test SEV Calculator against past incidents (Account Rentals, IDV bug, Open Profile abuse, Free Trial abuse) — deadline ~2026-04-09
- [ ] Hezus: Request data back-fill from October 2025 for back-testing
- [ ] Team: Draft comms for soft launch and usage guidance — after back-testing
- [ ] Hezus: Provide docs + GitHub links for tool — deadline ~2026-04-09
- [ ] Hezus: Finish scraping alert — deadline 2026-04-03

## Key Decisions

- Soft launch approach: tool as guidance for IM/SI teams, not an automated SEV trigger
- SEV requires both trajectory (steep ramp) AND minimum size — stable patterns don't qualify
- Cohort definition should use broader indicators rather than narrow segmentation
