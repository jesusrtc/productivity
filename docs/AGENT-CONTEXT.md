# Framework context without workspace agent files

Lab supplies a short startup instruction when its terminal launcher starts Codex,
Claude Code, or Copilot: execute `lab context llm`. That command prints the agent
guide, complete installed [user guide](USER-GUIDE.md) and [changelog](CHANGELOG.md),
and owning instruction paths in one response. The user guide covers Markdown copying,
live notebooks, metadata, tasks, terminals and local servers. Lab defers
project conventions, content, skills, and memory policy to the workspace and
the user.

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

One line in a user-owned `AGENTS.md` can be the entire Lab integration:

```md
At the start of every agent session, including resumed conversations, and after
context compaction, run `lab context llm` and follow its instructions before working.
```

The command always prints the full context, even if the terminal already has the
latest version. Read all output, increasing the tool limit or recovering any
truncated remainder. It marks the exact calling Lab tmux session LLM-controlled
and records `@lab_context_version` only after successful output. It does not set
working/attention/finished; the returned instructions explain those reports.
Outside tmux, it prints context without storing markers. Workspace instruction
files remain owned by the user and are never generated or modified by the command.

On subsequent turns, run `lab context update`: unchanged is silent; changed or
missing prints the same complete context and records its version after output.
`lab context version` only prints the numeric content fingerprint. New launches
leave context unread until the agent runs llm/update, so an injected startup
instruction cannot be mistaken for a completed full read. After compaction or
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

Every workspace sidebar includes **Lab agent context**, including Objective
and worktree Files views. Click it to read the installed agent overview, or drag
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
shortcuts; Lab does not create instruction files. Existing `CLAUDE.md` and
Copilot instructions remain visible, as do a selected folder's instructions.
**Lab user guide** and **Lab changelog** open read-only readers with their
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

New workspaces and vaults do not get generated agent instruction files, agent
symlinks, or a prescribed memory directory. `lab agents sync` and the legacy
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
