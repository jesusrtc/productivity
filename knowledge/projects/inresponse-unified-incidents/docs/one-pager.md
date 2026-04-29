# inResponse: Unify Cases and Incidents (One Pager)

## Background

Within Trust Investigations (TI), two groups use inResponse differently. Trust IM tracks its work as Incidents; the rest of TI tracks its work as TPD Trust Cases. Both start from an alert and follow similar workflows, but they are separate object types with divergent schemas, severity taxonomies, permissions, and reporting. Two narrower promotion targets, Inquiry and Threat Lookout, also exist alongside Cases and Incidents. Once an alert is promoted to any of these, the resulting object cannot be converted to another type without being re-filed by hand.

## Problem

The split is a source of recurring friction rather than a meaningful product distinction.

- **Wrong-type promotions are costly.** Once promoted, an alert cannot be converted, so the work is re-keyed into a new object by hand; context, comments, and timing data are lost or duplicated.
- **Two entities for one job doubles the surface area.** Runbooks, dashboards, permission reviews, severity thresholds, and Jira integrations fork along the Case/Incident axis despite near-identical workflows.
- **Downstream pain is filed.** [AIR-794](https://linkedin.atlassian.net/browse/AIR-794) exists because managers cannot roll up Jira tasks across types; [AIR-796](https://linkedin.atlassian.net/browse/AIR-796) tracks nst_cases schema gaps; Adan's triage-inconsistencies doc is in progress.

## Proposed Solution

Unify Cases and Incidents into a single object in inResponse. One schema, one lifecycle, one severity taxonomy. Any team-specific difference survives as an attribute on the unified object, not as a separate type.

The proposal itself is simple. The real work is understanding the blast radius: what today depends on the split and what breaks if it goes away. The open questions below capture what must be answered before committing to a plan.

## Open Questions

- **Backend delta:** once the shared incident table is accounted for, which fields, ACL rules, status states, and downstream consumers still differ in practice?
- **Scope:** unify two types (Case + Incident) only, or also fold in Inquiry and Threat Lookout?
- **Rollout shape:** switch all teams at once, one team at a time, or run both types side-by-side during a transition?
- **Severity convergence:** pick one of the three existing schemes or define a new shared one?
- **Naming:** keep "Incident" post-unification, or pick a neutral term acceptable to all groups?
- **Reporting continuity:** do SEV accounting, TPD load, and MTTR reports need parallel runs during the cutover?
- **Permissions:** is there any access guarantee that exists today only because of the type boundary, and if so, how do we preserve it?
- **TPD vs non-TPD distinction:** does "TPD" remain as a tag on the unified object, or does it stop being tracked?
- **On-call:** does each TI group continue to own its own triage queue, or do queues merge?
- **Training and runbooks:** what minimum set of docs needs to exist before rollout?
- **Timing:** is there a window that aligns with Project 2B, or should this follow it?
- **LOE and ROI:** once the impact above is understood, what is the explicit sizing from airp-web owners, and does the ROI justify the work versus better documentation of the current split?
- **Approval:** who is the single accountable decision-maker, and which managers must sign off before work starts?

## References

- airp-web backend: [enums.py](https://github.com/linkedin-multiproduct/airp-web/blob/master/airp-web/src/airpweb/models/enums.py) (CaseType, TPDCaseType, IssueType), [alert_resource.py](https://github.com/linkedin-multiproduct/airp-web/blob/master/airp-web/src/airpweb/api/alert_resource.py) (promotion code)
- JIRA: [AIR-794](https://linkedin.atlassian.net/browse/AIR-794) Synergy Intake, [AIR-796](https://linkedin.atlassian.net/browse/AIR-796) nst_cases gaps, [AIR-788](https://linkedin.atlassian.net/browse/AIR-788) ownership on promotion; [BDP-42067](https://linkedin.atlassian.net/browse/BDP-42067), [BDP-83492](https://linkedin.atlassian.net/browse/BDP-83492) OpenHouse migrations
- Adan: [Triage Inconsistencies Working Doc](https://docs.google.com/document/d/17XDdW21yjj-nbpJe5KkpF-rmiR9p43Tdw8Kio7-DNw0/edit), [Metric Definitions for InResponse Incidents and Cases](https://docs.google.com/document/d/1I13U3w2BQNyxkR2fdOq6zbLHVWYHObF1hH8kTjSN9EY/edit)
- [Trust Investigations OAD](https://docs.google.com/document/d/1sL7rvOvzCFYAzMKzGUuZKRZKTU0cFARykYbYx8r9AQ8/edit) (Felix Ng); [go/airpweb](https://linkedin.atlassian.net/wiki/spaces/ENGS/pages/525435694/LinkedIn+Abuse+Incident+Response+Platform+LI-AIRP); [go/inresponse](http://go/inresponse)
