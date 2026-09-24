# Attach confirmed terminal rows before live-list reconciliation

After successful session creation and autospawn persistence, the POST response
has enough persisted metadata to seed the owning session cache and start
attachment. Keep the fresh GET for enrichment, without an extra initial pill
repaint or a second attachment that would steal a later user selection.

This overlap needs per-workspace/vault read versions. Confirmed creation and
explicit close intent invalidate older reads. Otherwise a pre-create GET can
erase the new row, or a delayed creation refresh can resurrect a just-closed
tab. Keep the created-row fallback inside the refresh's publication, including
failed reads after cache invalidation: publishing an empty list and restoring
the row in the caller's next microtask can cancel an asset-loading attachment.
Actual close handlers and the real attachment preamble reproduce those races
in test_frontend_terminal_creation.py. Preserve Home association, captured
vault/workspace, final renderer geometry, fresh metadata and normal recovery.

Native creation results and all cold/latency failures are retained in
performance-progress.md. Faster warm creation does not establish cold creation
under 200 ms, steady-state typing improvement, or physical/iTerm parity.
