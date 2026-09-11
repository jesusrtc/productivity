# Terminal transport

Lab terminals are persistent tmux sessions bridged to the browser through a
PTY and WebSocket. The browser's input/output path is unchanged by socket
rotation: once attached, terminal bytes continue to travel directly between
the PTY and WebSocket event loop.

## Workspace renames and session identity

Rename a workspace from the secondary-click menu on either its vault row or
its top-level tab, or run `lab workspace rename <id> "New Named Workspace"`.
The folder becomes `workspaces/new-named-workspace`. Lab updates its own saved
paths, terminal links, and tab state. A conflicting destination is rejected.
An executing notebook must finish before its folder can move.

The workspace's internal ID stays fixed. `.lab/state/workspace-locations.json`
maps that ID to its current directory and can be rebuilt from workspace metadata.
Each terminal has a separate UUID, saved in the workspace's session list and
indexed in `.lab/state/session-index.json`. New tmux names use
`neurona-<uuidhex>`; display labels and workspace folder names do not determine
terminal identity. Neither a workspace rename nor a tab-label change creates
a replacement terminal.

Existing live sessions keep their transport names and sockets, and are adopted
into the UUID index without interruption. When later recreated, they use their
UUID transport name. Agent resume IDs remain separate and unchanged.

Lab repairs nested Git worktree links during a move. It does not rewrite
absolute paths embedded in user scripts, virtual-environment launchers, or a
running program's private state; those may need updating after a folder rename.

### Migration regression checks

Run `make test-all` for the CLI, backend, frontend behavior, latency, and
reconnect suites, then `make check-ui` for the running application's Chrome
smoke check. The focused migration tests are in
`core/tests/test_workspace_rename.py`: folder moves, cross-vault isolation,
collision rejection, rollback, Git worktree repair, missing-index recovery,
legacy-session adoption, repeated renames, stale notebook writes, deletion,
and UUID isolation when a deleted workspace ID is reused. They also launch a
real notebook kernel and a real tmux process on a disposable socket to verify
that variables, process identity, and working directories survive the move.

## Rolling socket rotation

macOS security and keychain context is captured by a long-lived tmux server
when that server starts. If a repaired client identity is visible in a fresh
iTerm process but not in existing Lab terminals, seed a new Lab tmux socket
from that working iTerm:

```bash
lab terminal rotate
```

Run the command directly in iTerm, not from inside tmux or a Lab terminal.
Lab then routes newly created terminals, Copilot sessions, managed workspace
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
workspace. The alias shares the source session's windows and panes; it does not
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

## Framework context in agent terminals

New Claude, Codex, and Copilot terminals use `lab agents run` to add the
packaged Lab capability guide while preserving each workspace's instructions.
The wrapper execs the agent; no persistent helper process or workspace agent
files are created. Plain shell tabs and attached sessions are unchanged.
See [Agent context](AGENT-CONTEXT.md) for manual launches and legacy-link cleanup.
