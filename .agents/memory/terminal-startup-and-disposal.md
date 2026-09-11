# Terminal startup and disposal

Lab lazy-loads `lab-app.js` after page load; `afterPageQuiet` can execute
synchronously when the page is already more than two seconds old. Keep the
view dispatch and workspace/default-Home startup at the end of the script,
after all state declarations. Otherwise Home can read `termCurrentWorkspaceId`
before initialization.

Vendored xterm 5.3 leaves viewport animation frames and timers queued when
a terminal is disposed. `_termGuardViewportDisposal` disables the disposed
viewport callbacks before renderer teardown, preventing the asynchronous
`dimensions` error. Keep the workaround outside immutable vendor assets;
reassess it when upgrading xterm. The real-Chrome lifecycle regression
reproduces the original error and covers queued refresh and reset frames.
