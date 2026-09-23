# Cold dashboard reads follow file dispatch, not file completion

On a cold workspace open, dispatch `_sidebarFetchWorkspaceFiles` first, then
start the independent dashboard batch while discovery is pending. Starting
dashboard requests before the file request can congest Chrome's connections;
waiting for file data and sidebar metadata needlessly serializes the reads.

The existing `_beforeRender` callback may start this batch earlier on the cold
path, but must run only once there. Warm/cache/background paths keep their
existing behavior. Observe the file promise even if the callback throws, and
still await its original result so errors and all file/root/generation guards
remain effective. Never paint the sidebar before the complete file data arrives.

An A/B/B/A comparison with four cold clicks per variant showed medians
180.5 → 154.4 ms, maxima 200.4 → 186.7 ms. File scan timings also varied;
do not attribute the whole click improvement to request overlap. Resource
timing independently confirmed that dashboard requests followed file dispatch
by ~0.1–0.3 ms instead of waiting for the full scan. Retain full workload and
terminal validation, all failures, and the same 200/50 ms budgets.
