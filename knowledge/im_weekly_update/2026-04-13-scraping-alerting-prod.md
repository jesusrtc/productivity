---
title: "IM Weekly Update - W16"
date: 2026-04-13
type: weekly-update
scope: org
projects: [alerting-migration, investigation-jss-feed, investigation-registration]
tags: [weekly-update]
---

Report for: jcortes@linkedin.com
Week: 2026-W16 (Mon Apr 13 - Fri Apr 17)

This Week's P0s:

This Weeks Work:
- Shipped the Scraping Alerting Revamp to production: split the monolithic scraping alert pipeline (33 sub-alerts, 6 categories) into 7 independent per-cohort egress notebooks backed by new retry, freshness, Iris, and execution-log widgets. 12 PRs merged across lipy-davi and im_playbooks; production mode enabled. Eliminates the silent failures that had been masking attacks. Design spec: https://docs.google.com/document/d/1Kp7ZSSpPuhFuA-FNjBcymzMNqUc1K110PnR9XhoPnek/edit
- Completed the Feed DIHE spike investigation with content-level analysis of the top 100 ATO accounts (responsible for 87% of the 20% T7D spike). Identified three fake-hiring scam brands running recruitment spam in LinkedIn Groups (cybercodersnetwork.com, beaconhire.net, rylemglobal.com) and quantified the restriction-whitelist defense gap — 15K blocked re-restrictions across 1,024 accounts that had already been correctly flagged. https://docs.google.com/document/d/1o9OpXqtmXepNvfTk3MwSI5ypZ2l_gJriP66xPVu8KHk/edit
- Closed out the Apr-7 registration spike investigation: a residential-proxy bot farm created 1,186 fake accounts using two Edge user-agents across 280+ IPs in 52 countries. Identified a Gmail-pattern email regex as a blocking signal and a challenge-gating gap that left 45 accounts unrestricted — recommended lix-gating for high-score accounts and handoff to abuse-platform team.

Next Weeks Work:
- DTO (out of office)
