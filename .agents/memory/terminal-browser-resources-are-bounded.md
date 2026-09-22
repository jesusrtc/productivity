# Terminal browser resources are bounded

Ordinary terminal views retain at most three hidden panes plus the active
pane. A single expiry timer releases parked panes after ten minutes even if
they are never revisited. Protect the requested cache entry while parking the
old active view so a warm switch does not evict its own target.

Eviction sends only the WebSocket detach control and disposes browser objects;
it never kills the tmux session or sends input. Running work and input remain
in tmux. Reopening an evicted view reattaches to the same session.

An active view is absent from _termCache, so full detach must dispose its
renderer/container directly. The xterm disposal guard also cancels the pane's
pending resize timer and disconnects its ResizeObserver. Empty/recovery overlays
must release those objects before clearing references.

WebGL callbacks capture the owning xterm rather than the mutable active pointer.
Activation failures, context loss and render errors dispose the addon, repaint
with the DOM renderer, and stop GPU retries for that page load.

The reported white sad-frame icon indicates a browser renderer failure; its
specific crash trigger was not proven. The resource leaks above were confirmed
in code and covered by test_frontend_terminal_resources.py, alongside the
real-Chrome viewport disposal and existing terminal switching tests.
