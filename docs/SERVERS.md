# Per-project dev servers

Lab has two connected layers for local development servers:

- A project-root `servers.json` declares the tabs, proxy destinations, and
  optional Start/Stop commands shown in the project's Servers modal.
- A conventional Makefile lets Lab supervise a project's main dev-server
  process from the dashboard and keep it alive.

## Server tabs and proxies: `servers.json`

Lab automatically reads `servers.json` from the root of each project. This is
the preferred place for agents and humans to configure local dev-server tabs,
proxying, and lifecycle commands.

```json
{
  "servers": [
    {
      "name": "app",
      "label": "Web app",
      "host": "localhost",
      "port": 5173,
      "path": "/",
      "mode": "proxy",
      "start_command": "make server-start",
      "stop_command": "make server-stop"
    }
  ]
}
```

`name` and `port` are required. `host` defaults to `localhost`, `path` to `/`,
and `mode` to `proxy`; `direct` is also supported. Start and stop commands are
optional, but when present they must be `make` commands. Missing commands leave
the corresponding modal controls disabled.

The Servers modal reads this file every time it opens. **Create servers.json**
writes a valid empty template (`{"servers": []}`) for an agent to fill. Use
**Reload file** if the agent edits it while the modal is already open.

For compatibility, Lab reads `project.json.proxies` only when `servers.json`
does not exist. The first save from the modal creates `servers.json` and makes
it the source of truth without modifying `project.json`.

## Managed server process: Makefile

A project can ask Lab to manage its main dev server (start it, keep it alive,
show its status) instead of you doing it by hand in a terminal.

### Opt in: add a Makefile

Drop a `Makefile` at the root of `projects/<id>/` with a `server-start`
target. That's the only requirement — Lab discovers it automatically.

```make
SERVER_PORT = 8006
SERVER_HEALTH_URL = http://127.0.0.1:8006/   # optional; defaults from SERVER_PORT

server-start:
	npm run dev -- --port $(SERVER_PORT)

server-stop:
	pkill -f "npm run dev" || true
```

- `server-start` must run in the **foreground** (it's launched inside a
  tmux session, not backgrounded with `&`).
- `server-stop` is optional, best-effort cleanup (e.g. killing strays).
  Its exit code is ignored.
- `SERVER_PORT` / `SERVER_HEALTH_URL` are both optional. With neither set,
  Lab only tracks whether the process is alive (no HTTP healthcheck).

### How it runs

Starting a server spawns a detached tmux session named like a terminal tab
(`neurona-<project>-server-<hash>`) running `make server-start`. The workspace
is deliberately omitted from the visible name but remains part of the
collision-resistant hash. It shows up in the normal terminal UI as a "server"
tab — `tmux attach` works on it like any other session. Stopping runs
`server-stop` (if present), then kills that tmux session.

Lab starts new managed servers on the active terminal socket. During a rolling
terminal-socket handoff, already-running servers remain on the draining socket
and keep working; status, stop, restart, and attach operations continue to
target their original socket. See [Terminal transport](TERMINALS.md).

### Health and auto-restart

A background supervisor checks every project every ~10s (`LAB_SERVER_SUPERVISOR_INTERVAL`):
liveness via `tmux has-session`, and — if a health URL is configured — an
HTTP GET with a ~2s timeout. Any HTTP response (even a 4xx/5xx) counts as
healthy; connection refused/timeout does not.

Each project has a **desired state** (`running` or `stopped`), saved at the
workspace-level `.lab/state/servers.json` (distinct from a project's proxy
configuration file). If desired is `running` and the session died, or its
health check fails for two ticks in a row, the supervisor restarts it. After
3 failed restarts in a row it backs off to at most one attempt per minute.
Closing the "server" tab from the terminal UI sets desired back to `stopped`
so it won't be resurrected.

### External servers

If the health URL answers but there's no lab-managed session (you started
the server by hand, outside Lab), it shows up as **external**: visible on
the dashboard with an Open link, never auto-restarted. Stopping it runs
`server-stop`, which cleans up the stray if the target covers it.

### Every registered workspace, not just the active one

Servers aren't scoped to whichever workspace you currently have open. The
dashboard (and the supervisor) cover every workspace listed in `lab
workspace list` (`~/.lab/workspaces.toml`) at once — start one project's
server in workspace A and another's in workspace B, and both show up
together, both get health-checked and auto-restarted on their own. A
workspace whose disk is unplugged or unreachable is just skipped for that
poll; everything else keeps working.

Each workspace keeps its own `.lab/state/servers.json` (desired state) and
its own tmux sessions — nothing about a project in one workspace touches
another.

### API

- `GET /api/servers` — every discovered project across every registered
  workspace, sorted by workspace then project. Each row carries
  `project_id`, `workspace` (which registered workspace it belongs to),
  `path`, `port`, `health_url`, `desired`, `status` (`stopped` /
  `starting` / `running` / `unhealthy` / `external`), `healthy`, `url`
  (non-null whenever the server is actually listening — what the
  dashboard's Open button uses), `session_name`, `session_created` (when
  the tmux session started, or `null` if it's not running), `attach_command`,
  and `restarts`.
- `POST /api/servers/{workspace}/{project_id}/start` / `.../stop` /
  `.../restart` — `{workspace}` is the id from `lab workspace list`. A
  workspace id that doesn't exist, or whose path isn't reachable right
  now, gives a 404 with a clear message.
- `GET /api/server-config?project_id=<id>&workspace=<workspace>` — effective
  proxy definitions and their source (`servers.json` or legacy project
  metadata).
- `PUT /api/server-config?project_id=<id>&workspace=<workspace>` — validate and
  write the project's canonical `servers.json`.
- `/api/workspace-proxy/{workspace}/{project_id}/{name}/…` — workspace-scoped
  HTTP mount used by embedded server tabs. The workspace stays in the path so
  relative assets keep the correct scope; legacy `/api/proxy/…` URLs remain
  available for old bookmarks.
