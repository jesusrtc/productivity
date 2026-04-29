# Scraping Alerting Revamp — One Pager

## Background
To detect logged-in scraping abuse following the PPFR launch, the Trust IM team built alerting ingested into InResponse, monitoring data egression, request volumes, and account cohorts. The current alert is a single monolithic pipeline covering 33 sub-alerts across 6 categories, hosted in a personal Darwin folder. It was never formally production-hardened, leading to two problems: the all-in-one alert lacks per-cohort separation for the anti-scraping team, and the pipeline has suffered repeated silent failures due to infrastructure fragility, upstream data gaps, and missing operational guardrails.

**The key failure modes are:**
- Transient Darwin issues (pip failures, scheduled job errors)
- Missing upstream data (BRBAE/BECDT gaps causing empty downstream tables)
- Silent failures (notebook completed successfully but produced zero alerts)
- WoW baseline distortion from upstream outages causing false positive and false negative alerts

## Proposed Solution
Split the egress alerts from the monolithic pipeline into 7 independent, production-hardened notebooks, one per member cohort plus one for BECDT egress, deployed in im_playbooks. Each notebook is independently schedulable, monitorable, and includes built-in resilience: query-level retry with exponential backoff, upstream data freshness validation, error-resilient batch execution with notification, and structured execution logging for watchdog monitoring.

The non-egress alert categories (Voyager, GraphQL, Identity Dash) remain in the existing notebook for now and will be evaluated for similar treatment in Phase 2.

## Phase 1

**New davi widgets (lipy-davi):**
- QueryWidget: SQL execution with configurable retry and exponential backoff, resolving the 9% transient failure rate
- DataFreshnessWidget: validates upstream table has recent data before computation, resolving the 14% upstream data failure rate
- TrustAlertBatchWidget: runs alert widgets safely, catches errors without halting pipeline, sends notification on failure, resolving the 17% silent failure rate
- TrustAlertIrisWidget: fires Trust Incidents via Iris with environment toggle (test/prod)
- TrustAlertExecutionLogWidget: append-only START/END logging for watchdog monitoring

**New alert notebooks (im_playbooks):**
- alert-scraping-egress-restricted.ipynb
- alert-scraping-egress-total.ipynb
- alert-scraping-egress-labeled.ipynb
- alert-scraping-egress-labeled-malicious.ipynb
- alert-scraping-egress-registered.ipynb
- alert-scraping-egress-registered-suspicious.ipynb
- alert-scraping-egress-becdt.ipynb

The monolithic notebook is limited to contain only Voyager, GraphQL, and Identity Dash alerts.

## Requirements
- Alerts live in im_playbooks, not personal Darwin folders
- Each cohort alert is independently schedulable and monitorable
- Query-level retry logic for Trino execution failures (3 retries with exponential backoff)
- Upstream data freshness validation before alert computation (halts on stale data rather than producing empty results)
- Execution logging enables watchdog monitoring from day one
- Error-resilient execution captures and notifies on widget failures without halting the entire pipeline

## Open Questions
- Upstream data ownership: Who owns backendcdtscrapinglabels and backendresponsebodyannotationevent? Need confirmed owners for escalation. APA-140942 (BRBAE migration to Kyoto) is still open.
- Phase 2 timeline: When will full GraphQL query parameter data be available in URE?
- Watchdog SLA: Is 24 hours the right target for pipeline failure triage?
- Watchdog notification channel: Use existing channel or create dedicated one (e.g., #im-alert-watchdog)?
