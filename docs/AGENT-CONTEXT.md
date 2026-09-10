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
workflow. The guide asks agents to read applicable workspace-owned instructions.

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
four Markdown resources, so installed wheels carry the same documentation.
Update the relevant topic when adding a framework capability. Keep client or
domain-specific rules in their owning workspace.
