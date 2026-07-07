# Terminal wheel scrolling: pass through to mouse-aware apps (2026-07-06)

Wheel routing for lab terminals lives in two halves:

- Client (`lab-app.js`): xterm.js is kept OUT of mouse-tracking mode
  (`_termStripModes` strips tmux's enable sequences so text selection works);
  a manual wheel listener on `#termBody` sends SGR wheel events straight to
  tmux over the WS.
- Server (`_configure_tmux_wheel_scrolling` in `term.py`): binds root
  `WheelUpPane` to `if-shell -F '#{||:#{pane_in_mode},#{mouse_any_flag}}'
  'send-keys -M' 'copy-mode -e'`.

Invariants — each guards against a bug we actually shipped:

1. **Apps that enable mouse reporting must receive the wheel events.**
   Claude Code (2.1.x) sets `mouse_any_flag` and scrolls its own transcript,
   like running it in iTerm. An earlier unconditional `copy-mode -eu` binding
   hijacked wheel-up into tmux copy-mode — the user saw stale pane history
   ("scrolling shows previous commands, can't read long responses").
2. **Never route scroll into arrow keys.** The stock tmux binding includes
   `alternate_on`, and `send -M` to an alt-screen pane without mouse mode
   becomes Up/Down arrows — which recalls prompt history in agent TUIs. We
   deliberately leave `alternate_on` out of the condition (moot for
   lab-spawned sessions anyway: `alternate-screen off` is set per session).
3. **No bare `send -M` fallback for panes without mouse mode** — it injects
   raw escape bytes into the shell and bash/readline executes garbage.
4. **`WheelDownPane` stays unbound** in the root table: tmux forwards unbound
   mouse keys to mouse-enabled panes on its own, copy-mode's table handles it
   while scrolled back, and shells just drop it.
5. **Codex (no mouse reporting) gets copy-mode line scrolling** — `copy-mode
   -e` (exit at bottom), not `-eu` (page-jump on entry, disorienting).

Regression test: `test_wheel_binding_passes_mouse_apps_through` in
`core/tests/test_term_routes.py`. The binding is server-global and re-applied
on every session spawn, so a code change here needs a lab server restart
(`launchctl kickstart -k gui/$UID/com.lab.server`) plus one session spawn (or
a manual `tmux bind-key`) to reach already-running sessions.

Related: [[terminal-latency-invariants]], [[lab-terminals-workspace-tmux-socket]].
