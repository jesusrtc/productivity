# Workspace history precedes view teardown

Call `history.pushState` while the outgoing workspace still has its live CSS
classes, before `_swapViewState` clears them. Chrome can synchronously flush
style/layout during the history update. After native editing of a large
document, clearing classes first produced 47–54 ms calls, including style
updates for about 36,600 elements. Moving history ahead of teardown removed
those intermediate updates in the measured trace (history maximum 3.1 ms).

Keep the same URL fields, hash, history state and entry count. `replace:true`
still skips the push; clear/park the old view before selecting the destination,
with terminal ownership still taken from the old workspace. Reapply an explicit
delete target only after teardown. Browser Back/Forward checks must verify
exact saved document content, sidebar roots and unchanged history IDs/URLs.

The fixture's `--document-history` reports command-to-verified-paint controller
round trips separately from timestamped clicks/keys. Those durations include
CDP overhead and are not physical display measurements. Reduced trace
categories and the completion metadata sidecar help check coverage without
the earlier verbose-trace truncation; retain uninstrumented latency results.
