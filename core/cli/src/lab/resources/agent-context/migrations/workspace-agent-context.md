# workspace-agent-context · Workspace-owned instructions

Lab now supplies framework capabilities at agent launch. Each workspace owns
its AGENTS.md, CLAUDE.md, skills and memory policy. Lab does not seed or link
those files automatically. `lab agents sync` is a read-only compatibility check.

Read and inspect first:

```bash
lab agent context
lab agents doctor
lab agents detach --root /absolute/vault --dry-run
```

When removal is part of the authorized task, use the same exact root:

```bash
lab agents detach --root /absolute/vault
```

Detach removes recognized legacy Lab links only. It preserves real instruction,
skill and memory files, custom link targets, and the original target files.
The command reports its audit path with the original symlink targets. Preserve
that audit for recovery; do not reconstruct links from guessed paths.

New launches use `lab agents run <agent> ...` to receive packaged capabilities.
`lab agent context` and `lab context` let an existing agent reread the guide.
Run `lab agents doctor` to verify setup. This catalog entry is informational;
`lab migrations` only prints guidance; it does not detach links or scan vaults.
