# Terminal polling preserves unchanged DOM

Workspace tabs, terminal tabs, and the active-terminal header cache their
rendered source markup on the owning DOM element. An unchanged poll must not
replace nodes, rebind listeners, dismiss tooltips, or destroy keyboard focus.
Compare generated markup rather than the browser-normalized `innerHTML`.
Keep generating markup so selection, labels, groups, dead-session state, and
recent-activity expiry still update. Clear the header cache when emptying it.

`scripts/perf/lab_ui_latency.mjs [url] [baseline-ref]` compares real DOM/layout
cost in an authenticated disposable browser. It uses 30 synthetic tabs and
never attaches or sends input to the user's terminals.
