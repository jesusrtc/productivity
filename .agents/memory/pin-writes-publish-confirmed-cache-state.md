# Pin writes publish confirmed cache state

After a successful Pin/Unpin metadata PUT, replace only the `pinned` field of
the latest `_workspaceSidebarCache` payload before the existing dashboard
refresh. Otherwise the warm refresh first paints the previous pin state and
the user waits for another file scan and metadata read before the shortcut
changes. Keep the normal fresh reconciliation; cached files are not a reason
to skip it. Do not create an incomplete payload if the cache is absent.

Capture the workspace path before the first metadata request and use that path
for the write and cache update. A delayed response must not write Alpha's
metadata into a newly selected Beta or repaint Beta's dashboard. Failed GETs
and PUTs must not publish the proposed pin state.

The native `--pins` latency fixture measures both original file buttons and
pinned-shortcut Unpin buttons, waits for the shortcut, ordinary button, cache
and dashboard to agree, and checks persisted metadata after each action. Exclude
`.sidebar-file-recent` when selecting ordinary rows: recent copies have a Git
history button in the same position. Hover is setup outside the click timing.
