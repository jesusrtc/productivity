# Terminal latency invariants (core server + lab UI)

Set up 2026-06-09 while making the terminal/UI low-latency. Three decisions
look "wrong" at first glance and are easy to regress:

1. **tmux endpoints in `core/src/core/routes/term.py` are sync `def`, not
   `async def` — on purpose.** They shell out to tmux with blocking
   `subprocess.run`; as `async def` those calls run ON the uvicorn event loop
   and stall every live terminal WebSocket (visible typing jitter every poll
   tick). Sync `def` makes FastAPI run them in its thread pool. Do not
   "modernize" them back to async without switching the subprocess calls to
   asyncio equivalents.

2. **Third-party UI libs are vendored, never CDN.** Everything lives in
   `core/src/core/static/vendor/<lib>@<version>/`, served with
   `Cache-Control: immutable` (version-stamped dirs make that safe). Adding a
   `<script src="https://cdn...">` to a template reintroduces network latency
   into app load and breaks offline. New libs: download into a new
   version-stamped dir.

3. **xterm.js WebGL renderer is attached to the ACTIVE session only**
   (`_termEnableWebgl`/`_termDisableWebgl` in `templates/index.html`).
   Browsers cap WebGL contexts (~8–16/page) and parked sessions stay alive in
   `_termCache`, so the GPU context is enabled on attach and disposed on
   park. Loading the addon once per terminal "for simplicity" will silently
   kill rendering after enough session switches.

4. **Terminal WebSockets must connect with the real geometry**
   (`/ws/term/<name>?cols=N&rows=N`; client fits before dialing and waits
   for layout on cold loads). Attaching at the 80x24 default makes tmux
   reflow the whole session twice (80x24 → real size), and the leftover
   partial redraws corrupt the pane — wrapped status lines mid-screen,
   "changes not shown" after switching agent pills/tabs. Same reason the
   client does a local `xterm.reset()` when reconnecting into an existing
   pane (purely client-side; tmux's attach replay repaints everything —
   do NOT send Ctrl-L to the app, that wipes claude's input line).

Also: the `/ws/term` PTY pump uses `loop.add_reader` on a non-blocking fd
(not executor reads), WS permessage-deflate is disabled in `main.py:run()`,
and `/` serves a render-cached HTML keyed by the template's mtime. Measured
after the change: ~3ms p50 keystroke echo through tmux, ~21ms warm session
switch, index page 4ms after first render.
