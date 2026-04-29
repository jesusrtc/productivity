---
title: "IM Weekly Update - W14"
date: 2026-03-31
type: weekly-update
scope: org
projects: [davi]
tags: [weekly-update]
---

Report for: jcortes@linkedin.com
Week: 2026-W14 (Mon Mar 31 - Fri Apr 4)

This Week's P0s:

This Weeks Work:
- Split the monolithic scraping alert into 7 independent per-cohort egress notebooks with safe SQL execution and automatic retry, replacing silent query failures with explicit error handling. This isolates alert logic per cohort for easier triage and reduces risk of unnoticed outages. https://docs.google.com/document/d/1Kp7ZSSpPuhFuA-FNjBcymzMNqUc1K110PnR9XhoPnek/edit?tab=t.0#heading=h.26cfm3c8jj1b
- Completed end-to-end testing of the scraping alert pipeline on Darwin, validating all DAVI widgets (data freshness checks, query retry, batch execution, Iris incident creation, execution logging) against live infrastructure. This confirms the new per-cohort alerting architecture works in production conditions. (lipy-davi#211, im_playbooks#506)
- Completed Project 2B (Negative Member ID) migration across all active ASTA jobs. Deployed and validated each in Holdem to meet the compliance deadline. Performed a final audit across all 29 IM-owned multiproducts to double check compliance. This ensures our abuse detection pipelines can process the upcoming negative member ID space without breaking.

Next Weeks Work:
- Oncall rotation
- SEV Calculator back-testing against past incidents (Account Rentals, IDV bug, Open Profile abuse, Free Trial abuse)
- One-pager and guidelines for SEV Calculator launch to broader team usage
