# Large-projects is Objectives staging

The user designated `large-projects` as the staging workspace for real UI tests
with simulated data and terminals. Reuse its six registered repository worktrees
and create clearly named owned fixtures. Its existing user terminals must keep
their metadata, running processes and input unchanged. Objective tests created
three dedicated `objective-staging-*` shells; send test input only to owned
sessions, never to the user's existing agents.

Measure the native UI with normal polling, external timestamped CDP input,
first samples retained, final content verified and a paint opportunity included.
Do not claim a universal 200 ms result from cached or synthetic handler timing.
