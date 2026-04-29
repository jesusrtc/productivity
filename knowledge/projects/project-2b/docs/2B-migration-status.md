# 2B Migration Status Report

> Generated: 2026-03-27 | All 29 MPs from abuse-short-term-action scope
> Last audit: 2026-03-27 (full codebase scan by Claude Code agents)

---

## Summary

| Metric | Count |
|--------|-------|
| Migration Complete (merged) | **5** |
| Main MP (fixes pushed to existing PR) | **1** |
| Migration In Progress (PR open, fixes pushed) | **5** |
| Not Needed (no member ID patterns) | **18** |
| Not Yet Scanned | **0** |
| Have member-id-utils | **5** |

---

## Migrated -- Complete (Merged to Master, sanity check passed)

| # | MP Name | Status | 2B PRs | member-id-utils | Agent Action (2026-03-27) |
|---|---------|--------|--------|-----------------|---------------------------|
| 1 | [airp-web](https://github.com/linkedin-multiproduct/airp-web) | **Done** | [#1451](https://github.com/linkedin-multiproduct/airp-web/pull/1451) merged, [#1419](https://github.com/linkedin-multiproduct/airp-web/pull/1419) merged | `member-id-utils-py 1.1.10` | Sanity PASSED. No missed patterns. Open PRs #1450/#1439/#1369 are redundant duplicates -- can be closed. |
| 2 | [lipy-davi](https://github.com/linkedin-multiproduct/lipy-davi) | **Done** | [#191](https://github.com/linkedin-multiproduct/lipy-davi/pull/191) merged, [#195](https://github.com/linkedin-multiproduct/lipy-davi/pull/195) merged, [#184](https://github.com/linkedin-multiproduct/lipy-davi/pull/184) merged | `member-id-utils-py 1.1.10` | **Pushed version bump** (1.1.6->1.1.10) to [PR #162](https://github.com/linkedin-multiproduct/lipy-davi/pull/162). 1 deferred SQL TODO in ip_activity_widget.py. |
| 3 | [lipy-invizor](https://github.com/linkedin-multiproduct/lipy-invizor) | **Done** | [#143](https://github.com/linkedin-multiproduct/lipy-invizor/pull/143) merged, [#145](https://github.com/linkedin-multiproduct/lipy-invizor/pull/145) merged | `member-id-utils-py 1.1.10` | Sanity PASSED. No missed patterns. get_id() correctly used, regex already `-?\d+`. |
| 4 | [im_playbooks](https://github.com/linkedin-multiproduct/im_playbooks) | **Done** | [#481](https://github.com/linkedin-multiproduct/im_playbooks/pull/481) merged | None | **Pushed fix** to [PR #488](https://github.com/linkedin-multiproduct/im_playbooks/pull/488): fixed `split(entityUrn,':')[4]` in prevalence_cuts notebook. 58 remaining patterns covered by [PR #443](https://github.com/linkedin-multiproduct/im_playbooks/pull/443) (30 files) -- merge #443 to complete. |
| 5 | [TSDashRepo](https://github.com/linkedin-multiproduct/TSDashRepo) | **Needs follow-up** | [#31](https://github.com/linkedin-multiproduct/TSDashRepo/pull/31) merged | `member-id-utils-py 0.0.38` | **Created [PR #53](https://github.com/linkedin-multiproduct/TSDashRepo/pull/53)**: found 2 MISSED bugs in IMTuplerDash.ipynb -- `re.findall(r'\d+')` and `re.sub(r'\D','')` corrupt negative IDs. Fixed regex to `-?\d+`. |

---

## Main MP -- abuse-short-term-action

| # | MP Name | Status | 2B PRs | member-id-utils | Agent Action (2026-03-27) |
|---|---------|--------|--------|-----------------|---------------------------|
| 6 | [abuse-short-term-action](https://github.com/linkedin-multiproduct/abuse-short-term-action) | **Fixes pushed** | [#506](https://github.com/linkedin-multiproduct/abuse-short-term-action/pull/506) open (author: `svc-mae-code`) -- fixes pushed on top | `member-id-utils-spark 1.1.10` | **Pushed fix to [PR #506](https://github.com/linkedin-multiproduct/abuse-short-term-action/pull/506)**: PR #506 covers 34 files (isMember filters, getIdFromMemberUrn, regex, deps, tests). Agent found 1 gap: `.cast('int')` on `getIdFromMemberUrn()` in FakeRomanceSuspiciousNameChangeAndReg.scala truncates negative IDs. Fixed + test added. 274 tests pass. PR #509 closed. |

---

## In Progress -- PR Open, Fixes Pushed by Agent

| # | MP Name | Status | 2B PRs | member-id-utils | Agent Action (2026-03-27) |
|---|---------|--------|--------|-----------------|---------------------------|
| 7 | [trust-diassociation-reassociation-pipelines](https://github.com/linkedin-multiproduct/trust-diassociation-reassociation-pipelines) | **Fixes pushed** | [#90](https://github.com/linkedin-multiproduct/trust-diassociation-reassociation-pipelines/pull/90) open | `member-id-utils-py 1.1.10` (branch) | **Pushed fixes to PR #90**: fixed 4 `isdigit()` calls in m2cread.py/m2cwrite.py -> `is_member()`. Added member-id-utils-py to product-spec.json + build.gradle. 25 tests, 97% coverage. **Rebased on master** to fix pre-merge failure (ligradle-python 4.2.13 EOL -> 4.2.19 ACTIVE). Ready for review. |
| 8 | [investigator-backend](https://github.com/linkedin-multiproduct/investigator-backend) | **Fixes ready (local)** | [#9](https://github.com/linkedin-multiproduct/investigator-backend/pull/9) open | None | **Committed locally**: Rust `u32`->`i64` for user_id, added `is_member()` fn + 7 unit tests. Push blocked -- repo is archived. Needs unarchive to push. |
| 9 | [frame-feature-anti-abuse](https://github.com/linkedin-multiproduct/frame-feature-anti-abuse) | **Fixes pushed** | [#544](https://github.com/linkedin-multiproduct/frame-feature-anti-abuse/pull/544) open (latest), [#504](https://github.com/linkedin-multiproduct/frame-feature-anti-abuse/pull/504) open (older), [#532](https://github.com/linkedin-multiproduct/frame-feature-anti-abuse/pull/532) merged | `member-id-utils-spark 1.1.10` + `member-id-utils-java 1.1.10` (in PR) | **Checked out PR #544** (latest open): covers 30+ MUST_FIX patterns across 9 modules (isMember filters, getIdFromMemberUrn URN parsing, abs() modulo fix, regex update, deps, ADU config). **Pushed 1 gap fix**: `split($"memberurn", ":").getItem(3)` in test file `GetAccountTieringOfflineAggregationTest.scala` -> `getIdFromMemberUrn`. Gradle build PASS. ADU config + product-spec.json + all build.gradle already updated by PR #544. |
| 10 | [account-integrity-investigation](https://github.com/linkedin-multiproduct/account-integrity-investigation) | **Fixes pushed** | [#32](https://github.com/linkedin-multiproduct/account-integrity-investigation/pull/32) open | `member-id-utils-spark 1.1.10` (added) | **Created [PR #32](https://github.com/linkedin-multiproduct/account-integrity-investigation/pull/32)**: applied Pattern S2 (`getIdFromMemberUrn` replacing `split($"target",":")` URN parsing in ProcessCsAuditLog.scala), Pattern P1/SQL1 (`is_member()` UDF replacing `member_id > 0` filter in asm_embedding_clustering.py with `MemberIdUdfs.registerAll()`). Added `member-id-utils-spark` to product-spec.json and both build.gradle files. Scala build PASS. |

---

## Not Needed -- No Member ID Patterns Found (Scanned by Agent)

All 18 MPs below were fully scanned by automated agents on 2026-03-27. No member ID validation, URN parsing, positivity guards, or type issues were found.

| # | MP Name | Last Updated | Agent Action (2026-03-27) | Reason |
|---|---------|-------------|---------------------------|--------|
| 10 | [airp](https://github.com/linkedin-multiproduct/airp) | 2025-12-15 | Scanned: **NOT NEEDED** | Stub repo. Only README + CI workflows. No source code. |
| 11 | [airp-backend](https://github.com/linkedin-multiproduct/airp-backend) | 2026-01-06 | Scanned: **NOT NEEDED** | Go HTTP scaffold (greet/admin/version). No member ID handling. |
| 12 | [airp-web-test](https://github.com/linkedin-multiproduct/airp-web-test) | 2026-02-08 | Scanned: **NOT NEEDED** | Flask test harness for auth flow. No member ID logic. |
| 13 | [airpnb](https://github.com/linkedin-multiproduct/airpnb) | 2026-03-14 | Scanned: **NOT NEEDED** | Notebook platform/infrastructure library. No member IDs. |
| 14 | [attck-alerts-airflow](https://github.com/linkedin-multiproduct/attck-alerts-airflow) | 2026-01-23 | Scanned: **NOT NEEDED** | Stub repo. Only README. No source code. |
| 15 | [coana-backend](https://github.com/linkedin-multiproduct/coana-backend) | 2026-02-08 | Scanned: **NOT NEEDED** | Python gRPC backend. member_urn used as opaque string only -- no parsing/validation. |
| 16 | [coana-frontend](https://github.com/linkedin-multiproduct/coana-frontend) | 2026-03-20 | Scanned: **NOT NEEDED** | React/Remix TS frontend. member_id typed as `string` -- inherently safe. |
| 17 | [coana-inv-frontend](https://github.com/linkedin-multiproduct/coana-inv-frontend) | 2025-03-04 | Scanned: **NOT NEEDED** | Stub repo. Only README + CI workflow. No source code. |
| 18 | [coana-web](https://github.com/linkedin-multiproduct/coana-web) | 2025-03-04 | Scanned: **NOT NEEDED** | Stub repo. Only README + CI workflow. No source code. |
| 19 | [flink-trust-dynamic-clustering](https://github.com/linkedin-multiproduct/flink-trust-dynamic-clustering) | 2026-03-23 | Scanned: **NOT NEEDED** | Flink clustering on behavioral signals. No member ID in clustering key or filters. |
| 20 | [inresponse-frontend](https://github.com/linkedin-multiproduct/inresponse-frontend) | 2026-02-05 | Scanned: **NOT NEEDED** | Frontend MP. Zero member ID references in 63 source files. |
| 21 | [samza-trust-distribution-model](https://github.com/linkedin-multiproduct/samza-trust-distribution-model) | 2026-03-23 | Scanned: **NOT NEEDED** | Samza scoring on traffic signals (SSL, TCP, timing). No member ID logic. |
| 22 | [threat-service](https://github.com/linkedin-multiproduct/threat-service) | 2026-03-14 | Scanned: **NOT NEEDED** | Flask SSO app. Auth via usernames, no member IDs. |
| 23 | [ti-attackdb](https://github.com/linkedin-multiproduct/ti-attackdb) | 2026-03-11 | Scanned: **NOT NEEDED** | Threat intel pipeline (actors, attacks, artifacts). No member IDs. |
| 24 | [transport-udfs-antiabuse-scores](https://github.com/linkedin-multiproduct/transport-udfs-antiabuse-scores) | 2026-03-11 | Scanned: **NOT NEEDED** | UDF library for network scores. member URN only in comments/test data as opaque string. |
| 25 | [trust-im-data-parity](https://github.com/linkedin-multiproduct/trust-im-data-parity) | 2026-02-08 | Scanned: **NOT NEEDED** | Empty skeleton Airflow DAG MP. No src/ directory, no DAGs, no code. |
| 26 | [trust-im-data-workflows](https://github.com/linkedin-multiproduct/trust-im-data-workflows) | 2025-03-17 | Scanned: **NOT NEEDED** | Stub repo. Only README + CI workflow. No source code. |
| 27 | [flashpoint_ingestion](https://github.com/linkedin-multiproduct/flashpoint_ingestion) | 2025-10-09 | Scanned: **NOT NEEDED** | Stub repo. Only README. No source code. |
| 28 | [trustinvtool](https://github.com/linkedin-multiproduct/trustinvtool) | 2025-03-13 | Scanned: **NOT NEEDED** | Stub repo. Only README + CI workflow. No source code. |

---

## Not Yet Scanned

| # | MP Name | Status | Agent Action (2026-03-27) |
|---|---------|--------|---------------------------|
| (none) | — | — | All MPs scanned. |
