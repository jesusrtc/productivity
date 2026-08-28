# Project notebook runtimes

Lab can run a project's notebooks on a host-local Jupyter kernel using the
client's exact Python environment. The notebook file, kernel session, and API
are shared by the browser UI and agents.

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

Notebook code cells are editable in place. Use **Run** or Cmd/Ctrl+Enter,
insert cells between existing cells, restart the kernel, or interrupt a long
cell. Drafts survive navigation. Every execution is written back to the real
`.ipynb`, including outputs and a stable nbformat cell id.

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

To rerun an existing cell safely, read `/api/nb?path=...` and send its stable
`cell_id` rather than a positional index. The same path always maps to the same
kernel, so variables persist across human and agent runs until restart.

Runtime API:

- `GET /api/nb/runtime?path=...` — desired/active status and build log
- `PUT /api/nb/runtime` — save `{path, spec}`
- `POST /api/nb/runtime/build` — build and validate `{path}`
- `GET /api/nb/session?path=...` — provider, session id, capabilities
- `POST /api/nb/session/restart` — wipe kernel state
- `POST /api/nb/session/interrupt` — interrupt a local running cell

Projects without `runtime.json` continue to use the existing Darwin provider.
