---
title: "IM Weekly Update - W15"
date: 2026-04-06
type: weekly-update
scope: org
projects: [davi, trust-im]
tags: [weekly-update]
---

Report for: jcortes@linkedin.com
Week: 2026-W15 (Mon Apr 6 - Fri Apr 10)

This Week's P0s:

This Weeks Work:
- Investigated a Feed DIHE spike (20% above baseline) as oncall. Attributed the increase to ATO Tier 1 and Tier 2 accounts driving group spam — fake recruitment posts across LinkedIn Groups from three scam brands. Identified the restriction whitelist gap as the key defense failure, allowing accounts to resume abuse after ID verification recovery. https://docs.google.com/document/d/1o9OpXqtmXepNvfTk3MwSI5ypZ2l_gJriP66xPVu8KHk/edit
- Investigated Telesign raising risk scores for all Italian phone numbers as oncall, blocking 83% of legitimate 2FA SMS delivery. Concluded no active attack after April 3 — the March spike was correctly handled but the scorer continued rejecting clean traffic. https://docs.google.com/document/d/1p_GZQ25hL8ZC5QMPWxxmkcyyiq-enPsoWg95nBECyQc/edit
- Investigated and took action on a fake account farm of 25K accounts hitting voyagerSocialDashReactions as oncall. Submitted mass action to restrict ~12K unrestricted accounts (52% were already caught by automated models). https://docs.google.com/document/d/1QDGGRc_GxrejmpphXePU8M9b0JOSGMoBvwL084cJG4Q/edit
- Wrote the Trust IM Sentinel one-pager — a proposal for unified operational health monitoring across all Trust IM products via a dedicated IRIS application and escalation plan. https://docs.google.com/document/d/1UH4-IkEh-oWeiVVYmLenFIYjdCWQ9GrUq63KR1Cc0lY/edit
- SEV Calculator back-testing: collecting past incidents and their cohorts to feed into the calculator (~70% complete).

Next Weeks Work:
- Continue Feed DIHE investigation — content analysis and whitelist window quantification
- Complete SEV Calculator back-testing and produce results
- SEV Calculator one-pager and guidelines for broader team usage
- Trust IM Sentinel IRIS configuration (Phase 1)
