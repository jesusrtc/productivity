# Connect using the final terminal renderer's fitted grid

Keep WebGL enablement before the final fit and WebSocket connection in the fresh
terminal path. Vendored xterm 5.3's DOM renderer uses fractional character width;
WebGL 0.16 floors device character width. A grid fitted before GPU activation
can have a different column count, even though its dimensions were valid.

An attempted socket/GPU overlap had no meaningful latency gain and failed a
real-Chrome geometry check: the initial connection grid differed from the active
GPU renderer. Restore visible open → fit → enable WebGL → clear → final fit in
_openWS → connect. Keep the no-valid-size retry and DOM fallback. The native
lifecycle test now compares connection and active-renderer grids in DOM and
real WebGL modes at three pane sizes, plus Unicode, focus and safe disposal.
Short correct echoes and positive dimensions alone do not prove the grid is
right. The rejected patch and evidence are in performance-progress.md.
