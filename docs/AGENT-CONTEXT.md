# Framework context and managed startup instructions

Lab supplies a short startup instruction when its terminal launcher starts Codex,
Claude Code, or Copilot: execute `lab context llm`. That command prints the agent
guide, complete installed [user guide](USER-GUIDE.md), changes since the terminal's
last [changelog](CHANGELOG.md) snapshot, and owning instruction paths in one response.
The same combined instructions/user guide appear as **Lab context** in META.
The user guide covers Markdown copying,
live notebooks, metadata, tasks, terminals and local servers. Lab defers
project conventions, content, skills, and memory policy to the workspace and
the user.

The packaged guide, launch bootstrap and managed instruction template also teach
Copilot, Codex and Claude to track each request with `lab agents work start`,
report their own changed files through `lab agents files record`, and finish the
assignment with a result summary before reporting terminal completion. These
request/delegation groups are independent of Objective tasks. Double-clicking
an agent opens the corresponding file-history modal. Tracking is explicit; it
does not infer attribution from another agent's dirty files or reconstruct
unreported historical work.

Delegating parents provide a focused brief, relevant user context, decisions,
constraints, permitted scope and expected results via `lab agents spawn
--context-file … --include-file …`. Lab injects the recorded parent context and
request identity, selected bounded references and the child's linked assignment
ID. Children resume that ID and follow the same reporting/context workflow when
further delegation is authorized. The raw parent conversation is not copied.
Client reloads receive these rules through the normal managed refresh; running
agents receive them with `lab context update`.

META lists existing scope-owned skill folders alongside instructions at the
vault, workspace, Objective and separately selected folder/worktree levels.
The paths checked at each root are `skills`, `content/skills`, `.agents/skills`,
`.claude/skills`, `.codex/skills`, `.github/skills`, `.copilot/skills` and the
backwards-compatible `.claude/commands`. This includes shared conventions and
older provider locations; a displayed path is not a claim that a provider has
loaded it. Current location references: [Codex](https://learn.chatgpt.com/docs/build-skills),
[Claude Code](https://code.claude.com/docs/en/skills), and
[Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).

Folders appear only when present. Their tree includes every nested directory
and file, including hidden and empty folders. Trees start folded and retain
expansion during ordinary refreshes while being viewed. After five continuous
minutes out of view, including a hidden browser tab or a different scope, the
tree and its nested folders fold automatically. Returning sooner keeps expansion.
File opening, context actions and dragging carry the owning root and relative
path. Symlinked skills retain that source path; ancestor cycles stop recursion.
Discovery reads only these skill directories, not the rest of the repository,
and does not create folders or load/execute skill instructions.

`GET /api/agents/context/files?path=/absolute/scope&include_skills=true` returns
`files` plus the nested `skills` tree; callers omitting the flag retain the
instruction-file array. The endpoint uses the explorer's existing scope access
checks. Use `lab api describe GET /api/agents/context/files` for the parameters,
`lab api call` to read it, or `lab ui` to expand its META folder summaries.

The installed `lab` package carries the guide and topic documentation. No
source-checkout path or symlink is needed. Read it from any directory:

```bash
lab context llm
lab context
lab context markdown
lab context notebooks
lab context servers
lab context meetings
lab context tasks
lab context user-guide
lab context changelog
lab context user-guide --path
lab context --path
```

The top-bar **↻ Update and restart Lab** button captures the current vault,
workspace and selected Objective, then refreshes their `AGENTS.md` files after
the new server starts. It creates missing files and places this section first:

```md
<!-- lab:managed-context:start -->
## Lab managed

Important: On startup, run `lab context llm`, read its full output and follow its instructions before working.
<!-- lab:managed-context:end -->
```

The template ships with Lab. Refresh replaces only complete marked sections,
consolidates duplicates and keeps all other instruction bytes in their original
order. Current files keep their modification time. Symlinks, non-files and
malformed markers are reported without replacement. Custom instructions belong
outside the markers. No other workspaces, Objectives or linked checkouts are
scanned; creating/opening a scope or reading context does not install this block.

The same explicit action is available without updating/restarting Lab:

```bash
lab agents refresh --vault /absolute/vault/path --workspace <id> --objective <id>
```

Omit `--objective` for vault/workspace, or both scope options for the vault only.
`POST /api/agents/context/refresh` accepts `vault` (registered ID), `workspace_id`
and `objective_id`; it requires administrator access because it includes vault
instructions. The CLI accepts a vault path. Refreshing files never submits a
message to running agents; their `lab context update` checks pick up changed
framework instructions.

Alternatively, one line in a user-owned `AGENTS.md` can be the entire integration:

```md
At the start of every agent session, including resumed conversations, and after
context compaction, run `lab context llm` and follow its instructions before working.
```

The command always prints the full agent instructions and user guide, even if
the terminal already has the latest version. Read all output, increasing the tool limit or recovering any
truncated remainder. It marks the exact calling Lab tmux session LLM-controlled
and records `@lab_context_version` only after successful output and snapshot storage. It does not set
working/attention/finished; the returned instructions explain those reports.
Outside tmux, it prints context without storing markers. Workspace instruction
files remain owned by the user and are never generated or modified by the command.

The changelog portion is a unified diff against the snapshot for this terminal's
last acknowledged version, not the complete history. No changelog changes means
no changelog section. With no prior snapshot, the command states that this read
establishes a baseline; it does not invent a diff. Snapshots live under
`$LAB_HOME/state/agent-context/` (default `~/.lab/state/agent-context/`) and contain
only framework changelog text. After stdout flushes, snapshot storage must succeed
before the live tmux option advances. Individual sessions acknowledge independently.
The full history stays available through `lab context changelog` and META.

On subsequent turns, run `lab context update`: unchanged is silent; changed or
missing prints full instructions/user guide plus only the changelog delta.
`lab context version` only prints the numeric content fingerprint. Launches
retain the previous acknowledged version for diffs, without treating it as proof
that a new conversation has read the instructions. After compaction or
starting a new conversation in the same tmux terminal, use `llm` unconditionally.
Plain `lab context` remains a read-only overview, without marker/version changes.

Lab's New agent buttons use this launcher automatically. In an ordinary shell:

```bash
lab agents run codex
lab agents run claude
lab agents run copilot
lab agents run codex -- resume --last
lab agents run --vault /absolute/vault/path copilot
lab agents run --vault /absolute/vault/path --workspace <id> --objective <id> codex
```

Arguments after `--` are passed to the provider. Lab terminal launches pin
`LAB_VAULT` to the terminal's owning vault and pass owning workspace/Objective
identities independently of a linked launch folder. Manual external launches
can specify `--workspace` and `--objective`; the process-local
`LAB_CONTEXT_WORKSPACE` and `LAB_CONTEXT_OBJECTIVE` retain them for subsequent
`lab context` reads. Plain shell tabs stay ordinary shells;
typing a provider's bare command in one bypasses this launcher. Existing running
agents are not interrupted or sent unsolicited messages; ask an existing agent
to run `lab context llm`, or start a new session to receive the startup instruction.
Claude resumes refresh their system prompt on versions supporting that option,
unless you explicitly request snapshot retention. Older versions receive the
append flag using their normal resume behavior. A fresh session is the simplest
way to discard old conversational instructions across providers.

Every workspace sidebar includes **Lab context**, including Objective
and worktree Files views. Click it to read the combined agent instructions and
full user guide, or drag
the shortcut or the reader's **Drag context to terminal** button onto a terminal
console to paste the full guide without submitting it. A packaged template adds
the owning vault, workspace and selected Objective instruction paths. Every
path is absolute, including the user guide and changelog for this installation.
It lists existing `AGENTS.md`, `agent.md`, `CLAUDE.md` and Copilot instruction
files and identifies the absolute source folder. The reader and drag retain their captured scope when
selection changes; another Objective or worktree gets its own rendered guide.
Switching terminals while the guide loads cancels the paste.

Workspace sidebars also show **Vault AGENTS.md**, **Workspace AGENTS.md**, and
**Objective AGENTS.md** for the current Objective. Each shortcut opens the
instruction file at its owning root, even when Files shows a linked worktree.
Switching Objectives updates the Objective shortcut. Only existing files have
shortcuts. An explicit instruction refresh creates missing `AGENTS.md` files.
Existing `CLAUDE.md` and
Copilot instructions remain visible, as do a selected folder's instructions.
The separate **Lab changelog** opens a read-only reader with its
absolute installation paths, even when the installed package is outside the
vault's explorer roots.

## How each provider receives context

- Codex: the launcher uses the local app-server `config/read` operation to read
  existing effective developer instructions, including trusted project config,
  then combines them with Lab's short bootstrap using a process-local `-c` override. This
  starts no model turn and writes no configuration. Repository `AGENTS.md`
  discovery stays enabled. Failure to read existing instructions produces an
  error instead of silently replacing them.
- Claude Code: `--append-system-prompt` adds the bootstrap with resolved paths. If the
  caller already supplied an append prompt or file, the launcher combines both.
  Existing repository instructions and all other launch options are preserved.
- Copilot: a process-local `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` includes the
  packaged `agent-context/bootstrap` directory containing `AGENTS.md`, retaining
  existing custom paths. Those instructions require the same `lab context llm`
  startup command. The process-local `LAB_AGENT_CONTEXT` retains the launch's
  scoped bootstrap and absolute references, but no separate environment read is needed.
  Provider home directories, authentication, and normal instruction discovery
  are unchanged.

The launcher does not impose workspace skills, a memory directory, or project
workflow. The guide requires every agent, including Objective and task agents,
to read the owning vault's root instructions and the owning workspace's root
instructions before working, unless already loaded. `LAB_VAULT` identifies the
owning vault; Objective/task context or workspace metadata identifies the
workspace. This applies even when the agent starts inside an Objective folder
or a linked repository/worktree, whose applicable instructions must also be read.
Existing `AGENTS.md` (or `agent.md`), `CLAUDE.md`, applicable Copilot instructions
and their referenced files retain their scope and ownership.

## Removing legacy integration links

Creating workspaces and vaults does not install agent instructions, agent
symlinks, or a prescribed memory directory. The explicit `lab agents refresh`
action manages only its marked `AGENTS.md` section. `lab agents sync` and the legacy
sync API are now read-only compatibility checks. `make setup` checks context
readiness instead of linking files. Settings offers **Check agent context**.

Inspect and remove recognized legacy Lab links:

```bash
lab agents detach --all-vaults --dry-run
lab agents detach --all-vaults
lab agents doctor
```

Use `--root /absolute/path` to target one vault or framework checkout. Migration
recognizes the old `CLAUDE.md → AGENTS.md`, Copilot instruction, shared skill,
and Claude memory redirect link layouts. It also recognizes the older shared
`content/skills/workspace-CLAUDE.md` target. Each link's original path and target
are recorded under `$LAB_HOME/state/agent-migrations/` (default `~/.lab/`) before
removal. An unavailable vault is reported and not treated as migrated.

Real instruction files, skill files, settings, and memory contents are preserved
byte-for-byte. Custom link targets and links inside symlinked directories are
left alone. In particular, existing real `AGENTS.md` files remain workspace-owned
even when an older Lab version originally generated them. Migration does not
commit or push changes in user vaults.

## Maintaining the guide

Operating guidance lives in `docs/USER-GUIDE.md`; dated changes live in
`docs/CHANGELOG.md`. ALWAYS update the user guide, changelog and relevant topic
with requested Lab changes, including operational guidance changes. The full
overview, short startup bootstrap and topic files live in
`core/cli/src/lab/resources/agent-context/`. Editable installs read canonical
checkout docs; wheel and source-distribution builds copy the same docs into
`lab/resources/docs/`. No separately maintained manual copies are needed.
Keep client or domain-specific rules in their owning workspace.
