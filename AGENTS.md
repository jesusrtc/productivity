# Lab framework repo

You're in the Lab framework source checkout. User vaults live in separate
repos and are selected through `lab vault` or `LAB_VAULT`.

## How to do anything

Use `lab`. Run `lab --help` for commands. Never hand-edit `workspace.json`, `tasks.json`, or `.index.json`.

## Where things live

- `core/` — framework-owned backend, UI assets, and package `core`. The persistent client port comes from the checkout's `.env` (`LAB_PORT`, templated by `.env.example`), falling back to the active vault's `lab.toml` (`[server].port`) and then `3333`; override per-run with `make start PORT=NNNN`. The actual port is recorded in the active vault at `.lab/state/server.port`. Resolve it from any tool, doc snippet, or curl command via `$(scripts/lab-url.sh)` — do **not** hardcode `localhost:3333`.
- `core/cli/` — framework-owned installable `lab` CLI.
- `apps/` — reserved for vault/client apps. Do not put framework internals here.
- `docs/` — framework docs, proposals, and migration notes.
- `scripts/` — framework helper scripts.
- `.claude/agents/` — shared framework agents.

## Notebooks

**When the user wants a notebook run to show up live in the Lab UI**, do NOT
bypass Lab with direct kernel execution. Use Lab's notebook executor so the cell appears
as soon as it starts and its timer and outputs stream to every open view:

```bash
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --code 'print(1+1)'
lab notebook exec workspaces/<id>/notebooks/<name>.ipynb --cell-id <id> --file /tmp/cell.py
```

The command sends the code through `POST /api/nb/exec` and waits for the final
result in the terminal; the notebook view updates while it waits. The kernel
session is pinned to the file path, so consecutive cells share state. To view
the running notebook, open `$(scripts/lab-url.sh)/#/nb?path=<path>`.

## On workspace work

Workspaces own their instructions, skills, and memory policy. Read applicable
workspace-owned `AGENTS.md` / `CLAUDE.md` files when present; Lab does not generate
or link them. Framework capability guidance is supplied by `lab agents run` at
launch and can be read with `lab context` (or `lab context markdown`,
`lab context notebooks`, `lab context servers`).

## On workspace server tabs

When a workspace needs one or more local-server tabs/proxies, agents may create
or edit `workspaces/<id>/servers.json`; do not add new proxy declarations to
`workspace.json`. The format is documented in `docs/SERVERS.md`. Lifecycle
commands in this file must be `make` commands.

## On sending an update

When the user (typically inside a `workspaces/<id>/`) asks to "send an update", "send a summary", or similar, write a markdown summary of what's been done to `content/updates/<yyyy-mm-dd>-summary.md` using today's date. Use one flat folder. If a file for today already exists, append a new section to it rather than overwriting. The folder is a user-curated knowledge artifact; we write the file, the user populates and consumes it.

## Workspace conventions

Use the conventions and skills provided by the selected vault. Framework
instructions do not prescribe a domain-specific workflow.


## Memory (repo-local — read at session start)

This repo carries its **own agent memory** under `.agents/memory/` — committed and
pushed with the code, **never** in `~/.claude`, `~/.codex`, or any tool's install
dir. This applies to every agent (Claude Code, Codex, Copilot):

- **At the start of a session**, read `.agents/memory/MEMORY.md` (the index) and
  load the linked files relevant to your task.
- **When you learn a durable fact** (a preference, a workspace constraint, a
  hard-won gotcha), append it as one file under `.agents/memory/` and add a
  one-line pointer to `MEMORY.md`. One fact per file.
- **Commit and push** memory changes along with your other work, so they travel
  with the repo.
- Monorepo-level memory lives at the root `.agents/memory/` (committed to the
  productivity repo); per-workspace memory lives at `workspaces/<id>/.agents/memory/`
  and travels with that workspace folder. Use whichever matches the scope of the fact.

This framework checkout's Claude Code auto-memory is redirected by its own
`.claude/settings.local.json` (`autoMemoryDirectory`) to the repo-local memory
directory. This is the framework repository's policy, not a policy imposed on
user workspaces. `lab agents sync` is now read-only; `lab agents detach` removes
recognized legacy instruction/skill links without touching their targets.
Do not write this repository's memory under `~/.claude`.
