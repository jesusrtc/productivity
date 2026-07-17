# Workspace architecture

Status: proposed

Last updated: 2026-07-17

## Decision summary

Neurona is the workspace shell. It renders files that exist in the workspace,
manages terminal sessions, provides clipboard and server surfaces, watches for
file changes, and presents workspace configuration. Neurona validates and
renders configuration; it does not mutate project trees. Projection changes
are applied by the user's coding agent, guided by a standard prompt
([agent-switch-prompt.md](agent-switch-prompt.md)).

Each workspace owns its conventions. It decides which agent surfaces, skills,
shared code, project templates, notebook providers, services, and UI features
its projects use. Projects contain their own work plus explicit projections
from their workspace. Neurona must not inject unexplained shared or META content
into project trees.

Notebook rendering is built into Neurona because `.ipynb` is a workspace file
format. Notebook execution is pluggable. Darwin, Jupyter, Spark, or another
executor implements a versioned notebook-provider protocol and is selected by
the workspace.

All rendered workspace files, including projected files and notebooks, update
live when their canonical source changes. Unsaved edits are never silently
overwritten.

The behavior of the current embedded Darwin executor is recorded in
[legacy/darwin-notebook-behavior.md](legacy/darwin-notebook-behavior.md) and is
the parity checklist for extracting Darwin into a provider.

## Ownership boundary

| Owner | Owns | Does not own |
| --- | --- | --- |
| Workspace | Project shape, shared sources, projections, supported agents, project features, notebook provider selection, repository and runtime policy, file-tree presentation | Filesystem mutation machinery, terminal implementation, or security |
| Project | Project files, project metadata, tasks, references, artifacts, PRs, worktree instances, and explicit project overrides | Copies of workspace-owned source files |
| Neurona | Workspace rendering, workspace editor, configuration validation, drift preview, file watching, live updates, terminal sessions, notebook storage/provider brokering, clipboard, server UI, indexing, and security | Agent conventions, Darwin behavior, project-tree mutation, or a mandatory project layout |
| User's agent | Applying projection changes to project trees — links, adapters, legacy adoption — guided by the switch prompt | Configuration schema, rendering, or removing files it cannot identify as projections |
| Provider app | Execution semantics for one capability, such as Darwin notebook execution | Workspace file ownership or UI policy |
| User preferences | Theme, tab order, open panels, and other personal display state | Workspace-wide project conventions |

## Proposed workspace structure

```text
<workspace-root>/
  workspace.json
  agents/
    instructions.md
    memory/
    roles/
  skills/
  code/
  templates/
    project/
      docs/
      notes/
  runtime/
  apps/
    notebook-darwin/
      lab-app.toml
      bin/notebook-darwin
  projects/
    example/
      project.json
      tasks.json
      docs/
      notebooks/
      AGENTS.md -> ../../agents/instructions.md
```

The physical names inside a workspace are tool-neutral where possible. The
workspace maps those sources to agent-specific surfaces such as `AGENTS.md`,
`CLAUDE.md`, `.claude/skills`, or Copilot prompt files.

Projects do not need a `workspace` field. Their containing workspace root is
the authority, and Neurona's existing workspace registry supplies the
cross-workspace identity used by Home and terminal routing.

## Workspace configuration

`workspace.json` at the workspace root is the declarative source of truth.
Users edit it through the Workspace tab; Neurona validates and writes it. The
file is not a place for arbitrary commands that run merely because a workspace
is opened. Executable capabilities are separately installed workspace apps and
are referenced by ID.

The current `lab.toml` already contains some workspace settings. Migration must
either fold those fields into `workspace.json` or extend `lab.toml` with this
schema. Neurona must not maintain two authoritative workspace configurations.

Illustrative configuration:

```json
{
  "version": 1,
  "id": "trust-safety",
  "name": "Trust & Safety",
  "agents": {
    "supported": ["claude", "codex", "copilot"],
    "default": "codex",
    "projections": [
      {
        "source": "agents/instructions.md",
        "target": "AGENTS.md",
        "mode": "symlink"
      },
      {
        "source": "agents/instructions.md",
        "target": "CLAUDE.md",
        "mode": "symlink",
        "when": "claude"
      },
      {
        "source": "agents/instructions.md",
        "target": ".github/copilot-instructions.md",
        "mode": "adapter",
        "when": "copilot"
      }
    ]
  },
  "project": {
    "template": "templates/project",
    "features": ["tasks", "docs", "notebooks", "prs", "diffs"],
    "mounts": [
      {
        "source": "skills",
        "target": ".agents/skills",
        "mode": "symlink"
      },
      {
        "source": "skills",
        "target": ".claude/skills",
        "mode": "symlink",
        "when": "claude"
      }
    ]
  },
  "notebooks": {
    "enabled": true,
    "provider": "darwin",
    "kernels": ["python3", "pyspark"],
    "mounts": [
      {
        "source": "code",
        "target": "code"
      }
    ]
  },
  "display": {
    "autoOpen": ["docs", "notebooks"],
    "hide": ["worktrees"],
    "showProjectionOrigin": true
  },
  "repositories": [],
  "services": []
}
```

## Workspace tab

The Workspace tab is the management surface for one workspace. It is a fixed,
always-visible tab (like the pinned Productivity tab), not something opened
per workspace: its content always reflects the currently selected workspace,
and switching workspaces re-renders it in place.

1. The file panel shows the real workspace root tree as it exists on disk. It
   does not inject framework-parent files, synthetic shared rows, or unrelated
   META from elsewhere.
2. The configuration panel controls supported agents, the default agent,
   projections, project features, notebook provider, services, and display
   rules.
3. A preview panel shows the effective project view and whether the on-disk
   state matches the configuration.

Project sidebars show only local project files and enabled workspace
projections. A projected entry displays its origin, for example:

```text
workspace/agents/instructions.md -> AGENTS.md
```

The UI must not use the vague label `(shared)` when the actual source is known.
Editing a workspace-owned file from any project opens the source in the
Workspace tab so the user understands that the change affects every associated
project.

## Agent-applied projections

Neurona does not implement projection apply machinery. Changing workspace
configuration edits `workspace.json` and nothing else. Bringing project trees
in line with the configuration — creating links, writing adapters, removing
stale projections, migrating legacy layouts — is done by the user's coding
agent working inside the workspace.

Switching agents is rare, so this stays a manual, agent-assisted step:

1. The user edits the configuration in the Workspace tab (for example,
   changing the default agent).
2. The Workspace tab compares configuration against disk and shows drift per
   project.
3. When drift exists, the tab offers the standard prompt from
   [agent-switch-prompt.md](agent-switch-prompt.md) to copy into the user's
   agent session.
4. The agent applies the changes, following the prompt's recommendations, and
   the user reviews the diff like any other agent work.
5. Neurona re-renders from disk; the drift indicator clears on its own.

The prompt is a recommendation, not a protocol. There are no plan IDs,
fingerprints, or managed-state stores; the agent's judgment plus the git diff
replace them. Neurona itself never overwrites or deletes project files.

## Agent and skill projections

Agent support is workspace policy, not a fixed Neurona enum. A workspace selects
the agent surfaces it supports and maps tool-neutral sources to those surfaces.
The mapping modes are conventions the user's agent applies:

- `symlink`: destination points directly to the workspace source.
- `adapter`: a small generated pointer file, marked as generated in its first
  line, for a tool that cannot consume the canonical source directly.
- `copy`: allowed only when a tool requires a physical copy; the generated
  file is clearly marked as generated.

The workspace also owns skill sources, repository imports, prefixes, memory
policy, hooks, and agent settings. Neurona validates those choices and renders
the resulting state; it does not choose `.claude/skills` or `.agents/memory`
as universal canonical locations.

## Generic notebook architecture

Notebook support has four layers:

1. **Notebook UI:** generic cells, Markdown, MIME outputs, insert/delete,
   drafts, copy, run state, and capability-driven controls.
2. **Notebook service:** safe path resolution, file locking, pending cells,
   nbformat persistence, session identity, and live file events.
3. **Provider protocol:** versioned execution, lifecycle, health, kernel, and
   output-event contract.
4. **Provider app:** Darwin, local Jupyter, remote Jupyter, Spark, or another
   executor installed in the workspace.

### Provider discovery

A workspace app registers as a notebook provider:

```toml
name = "notebook-darwin"
kind = "notebook-provider"
provider_id = "darwin"
protocol = 1
command = "bin/notebook-darwin"
```

Neurona communicates with providers out of process through a small JSON
protocol. Provider dependencies and failures therefore do not contaminate the
Neurona backend. `workspace.json` references `"provider": "darwin"`; it does
not repeat the provider command.

### Minimum provider contract

| Operation | Purpose | Required |
| --- | --- | --- |
| `capabilities` | Return kernels and support for execute, interrupt, restart, streaming, completion, or variables | Yes |
| `health` | Report availability, authentication, and actionable setup errors | Yes |
| `open` | Create or resolve the execution session for a notebook context | Yes |
| `execute` | Run code and emit standard notebook output events | Executable providers |
| `interrupt` | Stop the active cell without destroying the session | Capability |
| `restart` | Clear kernel state while retaining notebook cells | Capability |
| `close` | Release the provider session | Yes |

Execution events use standard notebook output shapes and MIME bundles:
`stream`, `display_data`, `execute_result`, and `error`. Neurona owns the
pending placeholder and final `.ipynb` write so all providers produce
consistent files and live-update behavior.

The UI reads provider capabilities rather than assuming Darwin:

- No provider: render, edit, and copy only.
- Execute only: show Run but not Interrupt or Restart.
- Streaming: update the pending cell as events arrive.
- Multiple kernels: show only kernels allowed by the workspace.
- Unhealthy provider: keep rendering the notebook and display actionable
  provider status.

### Darwin extraction

The current Darwin implementation remains in
`core/src/core/routes/nb_exec.py` until extraction. During the refactor:

1. Move generic locking, pending cells, nbformat persistence, and cell mutation
   into the Neurona notebook service.
2. Move Darwin CLI invocation, kernel lifecycle, exit-code mapping,
   bootstrapping, and code synchronization into `apps/notebook-darwin/`.
3. Make the current `/api/nb/exec` route a temporary compatibility adapter that
   resolves the workspace provider and delegates to the generic service.
4. Remove Darwin-specific labels and unconditional controls from the UI.
5. Validate the extracted provider against the legacy parity checklist.

Do not keep a copied executable implementation under `legacy/`. That would
create two sources that drift. The durable legacy behavior record is
`docs/legacy/darwin-notebook-behavior.md`; Git history preserves the old source.

## Generic live file updates

Live updates belong to Neurona's file-rendering layer, not to notebooks or a
specific provider.

### Canonical file identity

When Neurona opens a file, the read response includes:

- the requested workspace-relative path;
- the canonical source path after resolving a managed projection;
- the source version, such as an mtime/size tuple or content fingerprint;
- known project aliases for that source.

Sources and aliases are derived from on-disk symlinks plus the configured
projections; no separate managed-state record exists.

This is essential for workspace projections. Changing
`agents/instructions.md` must update open views of
`projects/a/AGENTS.md` and `projects/b/AGENTS.md` even though the symlink entries
themselves did not change.

### Path-aware events

The watcher emits a debounced, path-specific WebSocket event:

```json
{
  "type": "file-changed",
  "workspace": "trust-safety",
  "source": "agents/instructions.md",
  "aliases": [
    "projects/a/AGENTS.md",
    "projects/b/AGENTS.md"
  ],
  "change": "modified",
  "version": "1784301000.123:8421"
}
```

The client refreshes only open views whose canonical source or requested path
matches the event. This replaces the current coarse behavior where every
filesystem change broadcasts `index-updated` and may refresh the active file.

During migration both events are emitted: `file-changed` drives open views
while `index-updated` continues to drive tree and index refreshes. The primary
UI (`core/src/core/static/js/lab-app.js`) adopts `file-changed` first; the
secondary SPA views follow or are retired. `index-updated` is removed only
when nothing consumes it.

Watcher coverage is derived from the files Neurona can render: workspace roots,
project roots, configured projection sources, and active file parents. Large
dependency or checkout trees such as `.git`, `node_modules`, virtual
environments, repositories, and worktrees remain excluded. A lightweight
version poll is the fallback on filesystems where native watching is
unreliable.

### Renderer behavior

- Markdown, text, JSON, CSV, and code: fetch and re-render only when the version
  changed.
- Notebooks: reload committed cells and outputs while retaining scroll,
  collapsed outputs, and unsaved cell drafts.
- Images and PDFs: refresh with a versioned/cache-busted asset URL.
- HTML files: refresh a document iframe when it represents a file preview.
- Video/audio: preserve playback when possible; show an update indicator when
  a forced reload would lose state.
- Live server/proxy iframes: never auto-reload. They are stateful applications
  and retain an explicit Reload control.
- Deleted or moved files: show a clear state and refresh the containing tree.

If an open document has unsaved edits, Neurona never overwrites them. It shows:

```text
This file changed on disk.  Reload | Compare | Keep draft
```

Atomic-save sequences commonly appear as create-temp, modify, and rename
events. Neurona debounces and coalesces them into one logical change before
notifying clients.

## Home and project presentation

Home lists registered workspaces as clickable entries. Projects are grouped
under the workspace root that contains them. Clicking a workspace opens its
Workspace tab; clicking a project opens the project view.

The project tree contains:

- real project files;
- enabled workspace projections with their origin;
- enabled workspace features and service surfaces.

It does not contain hardcoded root `AGENTS.md`, `.claude`, `.agents`, shared
code, or META entries that the workspace did not enable.

## Terminals, servers, and clipboard

Neurona owns terminal session lifecycle and rendering. Workspaces may choose
supported agents and terminal profiles, but the terminal transport, reconnect,
session list, and persistence behavior remain Neurona infrastructure.

Workspaces declare services and how an installed service provider starts or
discovers them. Neurona renders status, controls, logs, links, and server UI; it
does not impose a Makefile convention on every project.

Clipboard operations remain a Neurona UI capability. They copy rendered text,
commands, URLs, images, or notebook cell content but do not alter workspace
ownership.

## Migration sequence

1. Add `workspace.json` schema validation to the existing workspace registry
   without changing projects.
2. Group Home projects by their containing registered workspace.
3. Build the Workspace tab and read-only effective projection preview.
4. Write the agent switch prompt and show it in the Workspace tab when
   configuration and disk drift.
5. Replace hardcoded shared sidebar entries with effective workspace
   projections.
6. Introduce canonical file identity and path-aware live updates.
7. Add notebook-provider discovery and the generic notebook service.
8. Extract Darwin into `apps/notebook-darwin/` and validate legacy parity.
9. Move project scaffolding, skill imports, server profiles, and display
   rules into workspace configuration; retire `lab agents sync` in favor of
   the agent switch prompt.
10. Remove compatibility paths after existing workspaces have migrated.

## Acceptance criteria

- Every project appears under its containing registered workspace in Home.
- The Workspace tab shows only the workspace source tree and its configuration.
- The project tree shows only local files plus enabled projections.
- Every projection displays its workspace source instead of `(shared)`.
- The Workspace tab shows drift between configuration and disk and offers the
  agent switch prompt.
- Neurona never mutates project trees; projection changes happen only through
  the user's agent.
- Agent support and defaults come from the workspace.
- Notebooks render with no execution provider installed.
- Darwin behavior works through a provider with legacy parity.
- Any rendered workspace file updates when its canonical source changes.
- Project aliases update when their workspace source changes.
- Unsaved drafts are protected from external changes.
- Live server views are not reloaded by unrelated filesystem events.
