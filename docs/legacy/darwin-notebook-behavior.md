# Legacy Darwin notebook behavior

Status: behavior snapshot for migration parity

Snapshot date: 2026-07-17

Current implementation:
`core/src/core/routes/nb_exec.py` and the notebook UI in
`core/src/core/static/js/lab-app.js`.

## Purpose

The current Neurona backend embeds Darwin-specific notebook execution. The
workspace architecture will extract that behavior into a workspace-installed
`notebook-darwin` provider while leaving generic notebook rendering and file
persistence in Neurona.

This document records behavior that must either remain in the generic notebook
service or be preserved by the Darwin provider. It is intentionally a behavior
record rather than a copied Python implementation.

## Current HTTP surface

### `GET /api/nb/session?path=<workspace-relative.ipynb>`

- Validates the notebook path.
- Returns the deterministic Darwin session assigned to the notebook path.
- The session name is `lab-` followed by the first 12 hexadecimal characters
  of the SHA-1 digest of the relative path.
- The same path therefore reuses kernel state across consecutive executions.

### `POST /api/nb/exec`

Request fields:

- `path`: workspace-relative `.ipynb` path.
- `code`: code to execute.
- `kernel`: optional Darwin kernel name.
- `timeout`: defaults to 1,800 seconds and has no artificial upper bound.
- `cell_index`: replace a committed cell.
- `insert_at`: insert a new cell at an index.

`cell_index` and `insert_at` are mutually exclusive. With neither, execution
appends a cell.

The route performs a three-phase operation:

1. Atomically write a pending cell into the notebook so the UI immediately
   shows which cell is running.
2. Run the Darwin command outside the FastAPI event loop.
3. Replace the pending cell with the returned outputs and execution count.

The response includes the path, session, Darwin kernel ID, execution count,
final cell index, parsed cell, and notebook mtime.

### `POST /api/nb/session/restart`

- Resolves the deterministic session for the path.
- Runs `darwin kernel restart --session <session>`.
- Treats “no kernel” or “not found” as a successful no-op because the next
  execution will create a fresh kernel.
- Wipes kernel variables without modifying notebook cells.

### `POST /api/nb/cell/delete`

- Deletes a committed cell by index.
- This is generic notebook-file behavior and should remain in Neurona rather
  than move to the Darwin provider.

## Path and file safety

- Paths must be relative to the workspace root.
- Absolute paths and `..` traversal are rejected.
- Only `.ipynb` paths are accepted.
- The resolved path must remain inside the workspace.
- Per-notebook locks protect local read-modify-write operations.
- Notebook writes use a sibling temporary file followed by `os.replace`.

These rules belong to the generic Neurona notebook service.

## Pending and running state

Before Darwin runs, Neurona writes a standard code cell with:

- the submitted source;
- the next anticipated execution count;
- empty outputs;
- `metadata.lab_pending = true`.

The file write wakes the workspace watcher, so open notebook views render a
running placeholder before remote execution finishes.

An in-memory set of active notebook paths provides an O(1) running-state check
for sidebar indicators. It is cleared on every success and failure path.

If Darwin infrastructure fails, the pending cell becomes an nbformat `error`
output rather than remaining stuck. This pending-cell lifecycle belongs to the
generic notebook service; provider errors supply the error name and message.

## Darwin CLI execution

Code is written to a temporary `.py` file and executed with:

```text
darwin code execute --file <temp.py> --session <session>
```

Optional arguments:

```text
--kernel <kernel>
--timeout <seconds>
```

The subprocess timeout is the requested timeout plus 30 seconds. The call runs
in a worker thread so slow kernels do not block the FastAPI event loop.

Successful stdout must be a JSON envelope. The current route consumes:

- `cell_outputs`;
- `kernel_id`;
- `execution_count`.

These Darwin-specific command and envelope details move to the provider.

## Darwin error mapping

Current exit handling:

| Condition | Current behavior |
| --- | --- |
| `darwin` missing | HTTP 503 with installation guidance |
| Process timeout | HTTP 504 |
| Invalid successful stdout JSON | HTTP 502 |
| Exit 2 | HTTP 401; Darwin authentication expired |
| Exit 5 | HTTP 503; pod not ready |
| Exit 6 | Convert the structured kernel error into an inline nbformat `error` output |
| Exit 7 | HTTP 503; kernel connection lost |
| Other non-zero exit | HTTP 500 with the tail of Darwin stderr/stdout |

Exit 6 is a successful notebook mutation from the UI's perspective: the code
ran and produced an error cell. Infrastructure failures fail the request after
converting the pending cell to an error.

The Darwin provider must preserve actionable errors, but the generic protocol
should expose typed provider errors instead of leaking Darwin exit codes into
Neurona.

## Notebook file semantics

When creating a notebook, the current implementation writes nbformat 4.5 with:

- a `python3` kernelspec;
- display name `Python 3 (Darwin)`;
- Python language metadata;
- an empty cell list.

Execution count defaults to the highest positive committed code-cell count plus
one. Darwin's positive execution count wins when returned.

Cells can be appended, replaced, or inserted. Returned `cell_outputs` are
stored directly as standard nbformat outputs. After writing, the route parses
the notebook through the same helper used by the read endpoint so its response
matches the renderer's cell shape.

Generic creation should stop hardcoding `Darwin` in the kernelspec display
name. The selected provider and kernel should supply kernelspec metadata.

## Shared `content/code` synchronization

The current embedded executor treats `content/code/` as an importable Python
package for Darwin notebooks.

### Bootstrap

On the first execution for a session, when `content/code/` exists, a hidden
Darwin execution:

- adds the pod home directory to `sys.path` so `~/code` is importable;
- evicts the standard-library `code` module if it was already imported and
  would shadow the workspace package;
- best-effort installs `lipy-davi` when `import davi` fails.

Bootstrap uses a 900-second timeout to tolerate pod startup and installation.
Failed bootstrap removes the in-memory bootstrap marker so a later call can
retry.

### File push

- Recursively scans `content/code/**/*.py`.
- Uses an in-memory mtime cache to push only new or modified files.
- Maps files to `/home/jovyan/code/` on the Darwin pod.
- Streams bytes as base64 through `darwin pod shell` rather than the Jupyter
  Contents API, because the kernel filesystem and Contents namespace differ.
- Creates parent directories before writing.
- Updates the mtime cache only after a successful remote write.

### Module reload

After pushing files, a hidden execution:

- calls `importlib.invalidate_caches()`;
- reloads already-imported modules in parent-before-child order;
- removes a module from `sys.modules` when reload fails;
- treats reload failure as best-effort rather than failing the user cell.

All bootstrap, push, and reload behavior is Darwin-provider behavior. In the
new architecture, the workspace supplies code mounts such as
`{"source": "code", "target": "code"}` and the provider implements how that
mount reaches its execution environment.

## Current notebook UI behavior

The current UI provides:

- rendered Markdown and standard notebook output types;
- syntax-highlighted code;
- HTML, image, error, stream, and rich MIME output rendering;
- Plotly activation for notebook output scripts;
- append and insert cell controls;
- source editing for committed and new cells;
- Run behavior for append, replace, and insert operations;
- cell deletion with confirmation;
- source and output copy controls;
- output collapse state;
- unsaved drafts stored in browser local storage;
- pending/running cell presentation;
- unseen-output indicators;
- a deterministic session badge;
- a Restart Kernel button with confirmation;
- scroll preservation during live updates.

Rendering, editing, draft preservation, copying, cell mutation, and live-update
behavior remain Neurona responsibilities. Provider name, session label, kernel
picker, Run, Interrupt, and Restart controls become capability-driven.

## Live update behavior

Today, notebook writes trigger the general workspace watcher, which broadcasts
the coarse `index-updated` event. The active notebook is then fetched and
rendered again while preserving scroll. A one-second project mtime poll is a
fallback.

The new file event layer replaces this with path-aware `file-changed` events
and canonical source identity. The notebook must continue to update after both
UI-triggered runs and provider/external writes, while retaining unsaved drafts
and output-collapse state.

## Coupling to remove

The following must not remain in Neurona's generic notebook route:

- Darwin command construction;
- Darwin exit-code knowledge;
- Darwin authentication and pod guidance;
- Darwin kernel names;
- `Python 3 (Darwin)` kernelspec text;
- `content/code` and `/home/jovyan/code` constants;
- `lipy-davi` installation;
- Darwin pod shell file transport;
- Darwin-specific restart commands;
- UI text that assumes every session is Darwin.

## Provider parity checklist

Before switching a workspace from the embedded executor to
`notebook-darwin`, verify:

- Same notebook path reuses the same provider session.
- Python, PySpark, Scala, R, and GPU kernel selection remains available where
  the installed Darwin CLI supports it.
- Long execution does not block unrelated Neurona requests.
- A pending cell appears before remote execution completes.
- Kernel exceptions render inline as notebook error outputs.
- Infrastructure failures replace the pending cell with an actionable error.
- Append, replace, and insert preserve their current semantics.
- Execution count remains stable.
- Standard MIME output rendering remains unchanged.
- Restart clears kernel state without modifying cells.
- Workspace code mounts preserve current bootstrap, push, and reload behavior.
- External or provider-driven notebook writes update every open view.
- Unsaved browser drafts survive live refreshes.
- The compatibility `/api/nb/exec` route delegates without changing existing
  callers during migration.

## Future source location

The extracted executable behavior should have one active home:

```text
apps/notebook-darwin/
  lab-app.toml
  bin/notebook-darwin
  tests/
```

The current `nb_exec.py` implementation stays active until the provider passes
this checklist. Then Darwin-specific code is moved, not copied, and the route
becomes a generic provider broker or compatibility adapter.

