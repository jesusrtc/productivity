# Framework context without workspace agent files

Lab supplies a small capability guide when its terminal launcher starts Codex,
Claude Code, or Copilot. The guide describes Markdown disclosures and copying,
live notebooks, Lab metadata commands, and local servers. It explicitly defers
project conventions, content, skills, and memory policy to the workspace and
the user.

The installed `lab` package carries the guide and topic documentation. No
source-checkout path or symlink is needed. Read it from any directory:

```bash
lab context
lab context markdown
lab context notebooks
lab context servers
lab context meetings
lab context tasks
lab context --path
```

Lab's New agent buttons use this launcher automatically. In an ordinary shell:

```bash
lab agents run codex
lab agents run claude
lab agents run copilot
lab agents run codex -- resume --last
lab agents run --vault /absolute/vault/path copilot
```

Arguments after `--` are passed to the provider. Lab terminal launches pin
`LAB_VAULT` to the terminal's owning vault. Plain shell tabs stay ordinary shells;
typing a provider's bare command in one bypasses this launcher. Existing running
agents are not interrupted or sent unsolicited messages; ask an existing agent
to read `lab context`, or start a new session to load the guide at startup.
Claude resumes refresh their system prompt on versions supporting that option,
unless you explicitly request snapshot retention. Older versions receive the
append flag using their normal resume behavior. A fresh session is the simplest
way to discard old conversational instructions across providers.

Every workspace sidebar includes **Lab agent context**, including Objective
and worktree Files views. Click it to read the installed launch guide, or drag
the shortcut or the reader's **Drag context to terminal** button onto a terminal
console to paste the full guide without submitting it. Switching terminals
while the guide loads cancels the paste.

## How each provider receives context

- Codex: the launcher uses the local app-server `config/read` operation to read
  existing effective developer instructions, including trusted project config,
  then combines them with Lab's guide using a process-local `-c` override. This
  starts no model turn and writes no configuration. Repository `AGENTS.md`
  discovery stays enabled. Failure to read existing instructions produces an
  error instead of silently replacing them.
- Claude Code: `--append-system-prompt-file` adds the packaged guide. If the
  caller already supplied an append prompt or file, the launcher combines both.
  Existing repository instructions and all other launch options are preserved.
- Copilot: a process-local `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` includes the
  packaged directory containing `AGENTS.md`, retaining existing custom paths.
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

The source is `core/cli/src/lab/resources/agent-context/`. The overview is kept
small; detailed examples belong in the topic files. Package data includes all
Markdown topic resources, so installed wheels carry the same documentation.
Update the relevant topic when adding a framework capability. Keep client or
domain-specific rules in their owning workspace.
