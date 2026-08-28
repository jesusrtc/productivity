# Project notebook runtimes

Lab can run a project's notebooks on a host-local Jupyter kernel using the
client's exact Python environment. The notebook file, kernel session, and API
are shared by the browser UI and agents.

## Create the notebook in the repository

Open the project or workspace Files sidebar and select **+ Notebook**. Choose
the repository folder and filename; Lab writes a valid `.ipynb` at that exact
location and opens it immediately. You can also secondary-click a folder and
choose **New notebook here**.

The repository file is the durable source of truth. Lab does not move the
notebook into a server-owned storage area: cells and outputs are written back
to the selected `.ipynb`. Each notebook path owns a dedicated kernel session,
so two notebook files do not share variables. Humans and agents share the
kernel only when they target the same path.

## Configure from the notebook

Open a `.ipynb` under `projects/<id>/`, select **Runtime**, and configure:

- **Managed by Lab**: choose a Python executable/version and package specs.
  Lab builds a versioned venv under `.lab/state/runtimes/<project>/`.
- **Existing Python**: provide the path to a client-managed Python environment.
  Lab validates it without installing or changing anything.
- Package pins, editable local libraries, required imports, CLI directories,
  CLI `--version`/health checks, environment variables, and working directory.

**Build & validate in Jupyter** starts a short-lived kernel with the selected
interpreter. Imports and CLI checks run inside that kernel, not in the Lab
server. A runtime only becomes active after every check passes.

Relative paths are resolved from `projects/<id>/`. Absolute client-host paths
are supported for existing interpreters, SDKs, CLI installations, and working
directories. Runtime configuration is stored in `projects/<id>/runtime.json`;
generated environments and build logs remain under `.lab/state/runtimes/`.

Libraries that invoke subprocesses work normally. The kernel process receives
the configured CLI directories on `PATH`, so Python such as
`subprocess.run(["client-cli", ...])` uses the same host tools a client would
run from their terminal. This execution path does not use Docker.

## Human workflow

Every project has a built-in **Jupyter** tab beside **Overview** and **Code
Search**. It opens the project's last-used notebook directly; when there is no
selection yet, it shows the project notebooks and a **+ Notebook** action. This
is part of Lab's own notebook runtime, so it does not require a `servers.json`
entry, host, port, reverse proxy, or separate JupyterLab process.

The launcher displays the current project name and path because notebooks are
project-scoped: a notebook created in project A appears in project A's Jupyter
tab, not project B's. From an open notebook, **All notebooks** returns to the
project launcher.

Notebook code cells are editable in place. Use **Run** or Cmd/Ctrl+Enter,
insert cells between existing cells, restart the kernel, or interrupt a long
cell. Drafts survive navigation. Every execution is written back to the real
`.ipynb`, including outputs and a stable nbformat cell id.

Notebook links use `#/nb?path=projects/<id>/<file>.ipynb`. When the project is
open in a cross-workspace tab, Lab resolves the path against that project's
owning workspace and carries the workspace id on every notebook request; it
does not accidentally execute a same-named path under the shell's active
workspace.

## Live agent and human execution

An execution is visible before it finishes, regardless of whether a person or
an agent started it:

1. Lab writes the created or modified cell to the `.ipynb` with a stable cell
   id, actor, start time, and running state.
2. Every open view receives ordered WebSocket events for the execution count,
   stdout/stderr, errors, rich HTML/SVG/PNG displays, `display_id` updates, and
   output clears. The cell shows its elapsed time while the kernel is busy.
3. Lab periodically checkpoints accumulated output to the notebook with atomic
   file replacement. The final event replaces the running cell with the exact
   completed nbformat outputs and timing metadata.

When a person reruns a cell, Lab immediately hides its previous output, keeps
the code/header in view, and shows a live-output placeholder. The first stream
event replaces that placeholder; rich output appears only when the kernel
actually emits it. If the execution request is rejected before it starts, the
previous output is restored unchanged.

`GET /api/nb/live?path=...` returns a complete snapshot of every run currently
in flight for that notebook. A newly opened or reconnected browser first
overlays this snapshot on the checkpointed file and then resumes WebSocket
deltas. Each run has a monotonically increasing sequence number; if the browser
detects a missing or out-of-order event, it reloads the snapshot instead of
showing incomplete output.

A disconnected or slow browser never blocks the kernel or another viewer. If
Lab or the kernel process exits mid-cell, the next notebook read preserves any
checkpointed output, marks the cell as stopped, and appends an `ExecutionLost`
error rather than leaving an immortal spinner.

The code currently executing is read-only in the browser so its displayed
source cannot diverge from the kernel request. After it finishes, the same cell
is editable and can be rerun. Unsaved browser drafts remain local while an
agent run is active and are not mistaken for the source actually executing.

## Agent workflow

Agents use the same endpoints as the browser:

```bash
curl -s -X POST "$(scripts/lab-url.sh)/api/nb/exec" \
  -H 'Content-Type: application/json' \
  -d '{
    "path":"projects/acme/notebooks/analysis.ipynb",
    "actor":"agent",
    "code":"from client_sdk import load_table\nprint(load_table())"
  }'
```

If the notebook's project is not in the server process's active workspace,
include its registered workspace id in the JSON body, for example
`"workspace":"local"`. Browser Run, interrupt, restart, runtime, and replay
requests add this automatically.

To rerun an existing cell safely, read `/api/nb?path=...` and send its stable
`cell_id` rather than a positional index. The same path always maps to the same
kernel, so variables persist across human and agent runs until restart.

Runtime API:

- `GET /api/nb/runtime?path=...` — desired/active status and build log
- `PUT /api/nb/runtime` — save `{path, spec}`
- `POST /api/nb/runtime/build` — build and validate `{path}`
- `GET /api/nb/session?path=...` — provider, session id, capabilities
- `GET /api/nb/live?path=...` — replayable in-flight execution snapshots
- `POST /api/nb/session/restart` — wipe kernel state
- `POST /api/nb/session/interrupt` — interrupt a local running cell

All authenticated clients also receive `notebook-execution` events on `/ws`.
The event phases are `started`, `execution-count`, `output`, `finished`,
`interrupted`, and `failed`; nonterminal deltas carry the run sequence and
stable cell id.

Projects without `runtime.json` continue to use the existing Darwin provider.
