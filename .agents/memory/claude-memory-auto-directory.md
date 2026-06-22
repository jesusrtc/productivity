# Claude Memory Uses Repo Path

For this repo, Claude Code auto-memory should write to `.agents/memory/` at the
repo root, or `projects/<id>/.agents/memory/` for project-scoped sessions.
`lab agents sync` writes ignored `.claude/settings.local.json` files with
`autoMemoryDirectory` pointing at those repo-local directories. The
`~/.claude/projects/.../memory` symlink is only a compatibility fallback for
older Claude installs and should not be treated as the source of truth.
