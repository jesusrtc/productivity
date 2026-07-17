# Agent switch prompt

Companion to [workspace-architecture.md](workspace-architecture.md).

When a workspace's agent configuration changes — a new default agent, an
added or removed supported agent, or a legacy workspace being adopted — the
projected files in project trees need to follow. Neurona does not do this
itself. Paste the prompt below into your coding agent (Claude Code, Codex,
Copilot) from the workspace root, let it work, and review the diff.

This happens rarely. The prompt is guidance and things to keep in mind, not a
script; the agent is expected to look at what is actually on disk before
changing anything.

## The prompt

```text
I changed this workspace's agent configuration. Bring the projected agent
files in line with it. Work from the workspace root. This is guidance, not a
script — check what is actually on disk first, and show me anything surprising
instead of forcing it.

Where things live:

- `workspace.json` at the workspace root declares the supported agents, the
  default agent, the projections (source → target mappings), and the skill
  mounts. Read it first; it is the source of truth.
- The canonical agent instructions are `agents/instructions.md`. Files like
  `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` must only
  ever be projections of that source, never independent copies.
- Apply projections at the workspace root and in every project under
  `projects/` that has a `project.json`.

What to do:

- For each projection enabled for a supported agent, make the target a
  relative symlink to the workspace source. Use a generated pointer file only
  for tools that cannot follow the canonical source, and mark it as generated
  in its first line.
- Mirror the configured skill mounts the same way (for example `skills` →
  `.agents/skills`, plus `.claude/skills` when Claude is supported).
- Remove projection targets that belong to agents no longer supported — but
  only when the target is a symlink into the workspace sources or a file
  carrying the generated marker. Anything else, leave it and report it.

Keep in mind:

- Never overwrite or delete a real file. If a projection target exists and is
  not a link into the workspace or a marked generated file, stop and show me
  the conflict.
- Legacy layouts exist: older workspaces have a real `AGENTS.md` at the root
  or inside a project, with `CLAUDE.md` linking to it. Move that content into
  `agents/instructions.md` first (merge, don't discard), then re-link both
  names to it.
- Use relative symlinks so links survive clones and directory moves.
- Agent memory stays inside the repo (`.agents/memory/`); never relocate it
  into `~/.claude` or another tool's install directory.
- Do not touch `repositories/`, worktrees, `.lab/`, or `.git/`.
- When you are done, list every link you created, replaced, or removed, and
  commit the change with a message noting the agent switch.
```

## After the agent runs

- Review the diff before committing anything you did not expect.
- Neurona needs no notification: it reads reality from disk, so open views and
  the Workspace tab update on their own.
