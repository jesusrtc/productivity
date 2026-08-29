# Terminal transport

Lab terminals are persistent tmux sessions bridged to the browser through a
PTY and WebSocket. The browser's input/output path is unchanged by socket
rotation: once attached, terminal bytes continue to travel directly between
the PTY and WebSocket event loop.

## Rolling socket rotation

macOS security and keychain context is captured by a long-lived tmux server
when that server starts. If a repaired client identity is visible in a fresh
iTerm process but not in existing Lab terminals, seed a new Lab tmux socket
from that working iTerm:

```bash
lab terminal rotate
```

Run the command directly in iTerm, not from inside tmux or a Lab terminal.
Lab then routes newly created terminals, Copilot sessions, managed project
servers, and proxy control sessions to the new socket. Existing sessions stay
attached to the previous socket and continue running without interruption.

To move only Copilot to the fresh security context, close its existing Lab
terminal tab and reopen it after the rotation. Other open terminal tabs do not
need to be restarted.

Inspect the current generations with:

```bash
lab terminal status
```

Rows are labeled `active` or `draining` and include the number of Lab
sessions on each socket. Attach commands returned by the API and UI include
`tmux -L <socket>` when a session is on a named socket.

## Attach an existing tmux session

Open **+ New**, paste an existing tmux session name into **Attach tmux
session**, and select **Attach**. Lab searches the active and draining socket
generations and creates a lightweight grouped-session alias inside the current
project. The alias shares the source session's windows and panes; it does not
start a nested tmux client or forwarding process.

Closing an attached Lab tab removes only this alias. The original tmux session
continues running. Attached aliases are not automatically recreated as plain
shells if the source later disappears; paste the source name again to reattach.
For access safety, importing a host tmux session that Lab does not already own
requires an administrator account.

## Resource and UX guarantees

- Steady state uses exactly one routed tmux server.
- During a handoff, routing is bounded to one active plus one draining server.
  A second rotation is refused until the old generation has drained.
- The draining route is removed automatically when its last Lab session
  closes. There is no keeper shell, watcher thread, polling daemon, or
  per-terminal helper process.
- The active named tmux server uses `exit-empty off` so its macOS security
  context remains available between terminal launches. This is one small,
  idle tmux process when no Lab sessions are open, not an accumulating pool.
- Session listing performs one tmux lookup in steady state and temporarily two
  during a drain. Keystrokes, output, scrolling, resizing, and reconnects do
  not perform socket discovery.
- Existing default-socket commands retain their original argv shape, so
  installations that never rotate behave exactly as before.

If the active named server exits unexpectedly, Lab does not silently recreate
it from the backend's older security context. New-session requests return a
clear error; run `lab terminal rotate` again from the working iTerm. Existing
sessions on any still-draining socket remain available.

The global routing file is `$LAB_HOME/tmux-sockets.json` (normally
`~/.lab/tmux-sockets.json`). It is atomically replaced and normalized to at
most two generations. Do not edit it by hand; use `lab terminal`.
