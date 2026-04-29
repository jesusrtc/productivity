# lipy-davi improvements log

Reverse-chronological log of quick improvements to [lipy-davi](repositories/lipy-davi) — the LinkedIn DAVI Python plotting library.

## How to use

- Prepend new entries (newest on top).
- Each entry: `## YYYY-MM-DD — Short title` with bullets for: **Why** (motivation), **What** (change summary), **Where** (files/modules touched), **PR/commit** (link once available), **Status** (idea / in-progress / merged).
- Keep entries tight — a few lines. This is a log, not a spec.

## Entries

## 2026-04-22 — Retry TrustAlertExecutionLogWidget.run() on transient infra failures

- **Why**: users hit intermittent infra errors calling `TrustAlertExecutionLogWidget(...).run()`; `%%safeql` already retries transient failures with the same pattern; widget should match.
- **What**: wrap `run()` in retry-with-sleep using safeql's defaults (3 attempts, 300s base backoff, exponential: `backoff * 2^attempt`). Re-raises original exception on final failure. Optional `retries` and `backoff` kwargs on `run()` for power-user overrides. Added 4 tests (success on attempt 1, success on attempt 2 after transient failure, all attempts exhausted, programmer error not retried).
- **Where**: `lipy-davi/src/linkedin/davi/widgets/trust_alert_execution_log_widget.py:25-57`; new test file `lipy-davi/test/widgets/test_trust_alert_execution_log_widget.py`
- **PR/commit**: _pending_
- **Status**: in-progress
