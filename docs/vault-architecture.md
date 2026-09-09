# Vault architecture

Status: proposed

Last updated: 2026-07-17

## Decision summary

Neurona is the vault shell. It renders files that exist in the vault,
manages terminal sessions, provides clipboard and server surfaces, watches for
file changes, and presents vault configuration. Neurona validates and
renders configuration; it does not mutate workspace trees. Projection changes
are applied by the user's coding agent, guided by a standard prompt
([agent-switch-prompt.md](agent-switch-prompt.md)).

Each vault owns its conventions. It decides which agent surfaces, skills,
shared code, workspace templates, notebook providers, services, and UI features
its workspaces use. Workspaces contain their own work plus explicit projections
from their vault. Neurona must not inject unexplained shared or META content
into workspace trees.

Notebook rendering is built into Neurona because `.ipynb` is a vault file
format. Notebook execution is pluggable. Jupyter, Spark, or another
executor implements a versioned notebook-provider protocol and is selected by
the vault.

All rendered vault files, including projected files and notebooks, update
live when their canonical source changes. Unsaved edits are never silently
overwritten.

## Ownership boundary

| Owner | Owns | Does not own |
| --- | --- | --- |
| Vault | Workspace shape, shared sources, projections, supported agents, workspace features, notebook provider selection, repository and runtime policy, file-tree presentation | Filesystem mutation machinery, terminal implementation, or security |
| Workspace | Workspace files, workspace metadata, tasks, references, artifacts, PRs, worktree instances, and explicit workspace overrides | Copies of vault-owned source files |
| Neurona | Vault rendering, vault editor, configuration validation, drift preview, file watching, live updates, terminal sessions, notebook storage/provider brokering, clipboard, server UI, indexing, and security | Agent conventions, workspace-tree mutation, or a mandatory workspace layout |
| User's agent | Applying projection changes to workspace trees — links, adapters, legacy adoption — guided by the switch prompt | Configuration schema, rendering, or removing files it cannot identify as projections |
| Provider app | Execution semantics for one capability, such as Jupyter notebook execution | Vault file ownership or UI policy |
| User preferences | Theme, tab order, open panels, and other personal display state | Vault-wide workspace conventions |

## Proposed vault structure

```text
<vault-root>/
  vault.json
  agents/
    instructions.md
    memory/
    roles/
  skills/
  code/
  templates/
    workspace/
      docs/
      notes/
  runtime/
  apps/
    notebook-local/
      lab-app.toml
      bin/notebook-local
  workspaces/
    example/
      workspace.json
      tasks.json
      docs/
      notebooks/
      AGENTS.md -> ../../agents/instructions.md
```

The physical names inside a vault are tool-neutral where possible. The
vault maps those sources to agent-specific surfaces such as `AGENTS.md`,
`CLAUDE.md`, `.claude/skills`, or Copilot prompt files.

Workspaces do not need a `vault` field. Their containing vault root is
the authority, and Neurona's existing vault registry supplies the
cross-vault identity used by Home and terminal routing.

## Vault configuration

`vault.json` at the vault root is the declarative source of truth.
Users edit it through the Vault tab; Neurona validates and writes it. The
file is not a place for arbitrary commands that run merely because a vault
is opened. Executable capabilities are separately installed vault apps and
are referenced by ID.

The current `lab.toml` already contains some vault settings. Migration must
either fold those fields into `vault.json` or extend `lab.toml` with this
schema. Neurona must not maintain two authoritative vault configurations.

Illustrative configuration:

```json
{
  "version": 1,
  "id": "example-vault",
  "name": "Example vault",
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
  "workspace": {
    "template": "templates/workspace",
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
    "provider": "local",
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

## Vault tab

The Vault tab is the management surface for one vault. It is a fixed,
always-visible tab (like the pinned Productivity tab), not something opened
per vault: its content always reflects the currently selected vault,
and switching vaults re-renders it in place.

1. The file panel shows the real vault root tree as it exists on disk. It
   does not inject framework-parent files, synthetic shared rows, or unrelated
   META from elsewhere.
2. The configuration panel controls supported agents, the default agent,
   projections, workspace features, notebook provider, services, and display
   rules.
3. A preview panel shows the effective workspace view and whether the on-disk
   state matches the configuration.
4. The right-docked terminal is scoped to the vault root and keeps its own
   saved sessions under the ``__vault__`` pseudo-workspace. The Agents card
   controls which of Claude Code, Codex, and Copilot appear in terminal and
   settings menus; at least one agent must remain enabled.

Workspace sidebars show only local workspace files and enabled vault
projections. A projected entry displays its origin, for example:

```text
vault/agents/instructions.md -> AGENTS.md
```

The UI must not use the vague label `(shared)` when the actual source is known.
Editing a vault-owned file from any workspace opens the source in the
Vault tab so the user understands that the change affects every associated
workspace.

## Agent-applied projections

Neurona does not implement projection apply machinery. Changing vault
configuration edits `vault.json` and nothing else. Bringing workspace trees
in line with the configuration — creating links, writing adapters, removing
stale projections, migrating legacy layouts — is done by the user's coding
agent working inside the vault.

Switching agents is rare, so this stays a manual, agent-assisted step:

1. The user edits the configuration in the Vault tab (for example,
   changing the default agent).
2. The Vault tab compares configuration against disk and shows drift per
   workspace.
3. When drift exists, the tab offers the standard prompt from
   [agent-switch-prompt.md](agent-switch-prompt.md) to copy into the user's
   agent session.
4. The agent applies the changes, following the prompt's recommendations, and
   the user reviews the diff like any other agent work.
5. Neurona re-renders from disk; the drift indicator clears on its own.

The prompt is a recommendation, not a protocol. There are no plan IDs,
fingerprints, or managed-state stores; the agent's judgment plus the git diff
replace them. Neurona itself never overwrites or deletes workspace files.

## Agent and skill projections

Agent support is vault policy, not a fixed Neurona enum. A vault selects
the agent surfaces it supports and maps tool-neutral sources to those surfaces.
The mapping modes are conventions the user's agent applies:

- `symlink`: destination points directly to the vault source.
- `adapter`: a small generated pointer file, marked as generated in its first
  line, for a tool that cannot consume the canonical source directly.
- `copy`: allowed only when a tool requires a physical copy; the generated
  file is clearly marked as generated.

The vault also owns skill sources, repository imports, prefixes, memory
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
4. **Provider app:** Local Jupyter, remote Jupyter, Spark, or another
   executor installed in the vault.

### Provider discovery

A vault app registers as a notebook provider:

```toml
name = "notebook-local"
kind = "notebook-provider"
provider_id = "local"
protocol = 1
command = "bin/notebook-local"
```

Neurona communicates with providers out of process through a small JSON
protocol. Provider dependencies and failures therefore do not contaminate the
Neurona backend. `vault.json` references `"provider": "local"`; it does
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

The UI reads provider capabilities rather than assuming Jupyter:

- No provider: render, edit, and copy only.
- Execute only: show Run but not Interrupt or Restart.
- Streaming: update the pending cell as events arrive.
- Multiple kernels: show only kernels allowed by the vault.
- Unhealthy provider: keep rendering the notebook and display actionable
  provider status.

## Generic live file updates

Live updates belong to Neurona's file-rendering layer, not to notebooks or a
specific provider.

### Canonical file identity

When Neurona opens a file, the read response includes:

- the requested vault-relative path;
- the canonical source path after resolving a managed projection;
- the source version, such as an mtime/size tuple or content fingerprint;
- known workspace aliases for that source.

Sources and aliases are derived from on-disk symlinks plus the configured
projections; no separate managed-state record exists.

This is essential for vault projections. Changing
`agents/instructions.md` must update open views of
`workspaces/a/AGENTS.md` and `workspaces/b/AGENTS.md` even though the symlink entries
themselves did not change.

### Path-aware events

The watcher emits a debounced, path-specific WebSocket event:

```json
{
  "type": "file-changed",
  "vault": "example-vault",
  "source": "agents/instructions.md",
  "aliases": [
    "workspaces/a/AGENTS.md",
    "workspaces/b/AGENTS.md"
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

Watcher coverage is derived from the files Neurona can render: vault roots,
workspace roots, configured projection sources, and active file parents. Large
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

## Home and workspace presentation

Home lists registered vaults as clickable entries. Workspaces are grouped
under the vault root that contains them. Clicking a vault opens its
Vault tab; clicking a workspace opens the workspace view.

The workspace tree contains:

- real workspace files;
- enabled vault projections with their origin;
- enabled vault features and service surfaces.

It does not contain hardcoded root `AGENTS.md`, `.claude`, `.agents`, shared
code, or META entries that the vault did not enable.

## Terminals, servers, and clipboard

Neurona owns terminal session lifecycle and rendering. Vaults may choose
supported agents and terminal profiles, but the terminal transport, reconnect,
session list, and persistence behavior remain Neurona infrastructure.

Vaults declare services and how an installed service provider starts or
discovers them. Neurona renders status, controls, logs, links, and server UI; it
does not impose a Makefile convention on every workspace.

Clipboard operations remain a Neurona UI capability. They copy rendered text,
commands, URLs, images, or notebook cell content but do not alter vault
ownership.

## Migration sequence

Status (2026-07-18): steps 1–2 are done; step 3 shipped in v1 — the fixed
Vault tab with the vault tree, configuration/agents/workspaces cards,
starter-file bootstrap, the agent setup prompt, per-vault agent
availability, and a vault-rooted terminal — with the projection preview
still to come. Step 4's prompt exists (agent-switch-prompt.md plus the
in-card setup prompt); drift detection does not yet. Step 5 shipped in v1
for the workspace sidebar's Meta section: vaults that declare
`agents.projections` / `workspace.mounts` get origin-labeled rows
("CLAUDE.md ← AGENTS.md") instead of the legacy "(shared)" entries, which
remain the fallback for undeclared vaults.

1. Add `vault.json` schema validation to the existing vault registry
   without changing workspaces.
2. Group Home workspaces by their containing registered vault.
3. Build the Vault tab and read-only effective projection preview.
4. Write the agent switch prompt and show it in the Vault tab when
   configuration and disk drift.
5. Replace hardcoded shared sidebar entries with effective vault
   projections.
6. Introduce canonical file identity and path-aware live updates.
7. Add notebook-provider discovery and the generic notebook service.
8. Validate notebook execution against the provider protocol.
9. Move workspace scaffolding, skill imports, server profiles, and display
   rules into vault configuration; retire `lab agents sync` in favor of
   the agent switch prompt.
10. Remove compatibility paths after existing vaults have migrated.

## Acceptance criteria

- Every workspace appears under its containing registered vault in Home.
- The Vault tab shows only the vault source tree and its configuration.
- The workspace tree shows only local files plus enabled projections.
- Every projection displays its vault source instead of `(shared)`.
- The Vault tab shows drift between configuration and disk and offers the
  agent switch prompt.
- Neurona never mutates workspace trees; projection changes happen only through
  the user's agent.
- Agent support and defaults come from the vault.
- Notebooks render with no execution provider installed.
- Jupyter behavior works through a provider with the notebook protocol.
- Any rendered vault file updates when its canonical source changes.
- Workspace aliases update when their vault source changes.
- Unsaved drafts are protected from external changes.
- Live server views are not reloaded by unrelated filesystem events.
