# Lab

Lab is a local productivity framework: this repo owns the CLI, backend, UI, tests, and packaging. User work lives in separate vault repos created with `lab init`.

## Install

```bash
make install
```

This installs editable `lab` and `core` shims into `~/.local/bin/`. Keep that directory on your `PATH`.

## First Run

```bash
lab init ~/work/my-lab
cd ~/work/my-lab
lab start
```

`lab init` creates a vault repo with `workspaces/`, `content/`, `docs/`, `skills/`, `scripts/`, `apps/`, `repositories/`, `.agents/memory/`, and vault-local `.lab/state/`.

Use `lab vault list` and `lab vault use <path>` to select the default vault. In the UI, workspaces from multiple vaults can remain open together. Home is the permanent framework destination; Assistant manages tasks across vaults.

The naming hierarchy is **Vault → Workspace → Terminal**. See [Naming and compatibility](docs/NAMING.md) for commands, configuration, and support for existing Local and SSD vaults.

## Layout

- `core/cli/` - installable `lab` CLI.
- `core/` - FastAPI/WS backend, UI assets, and framework-owned CLI.
- `apps/` - reserved for vault/client apps; framework code should not live here.
- `docs/productivity-framework-proposal.md` - vault/framework split proposal and migration plan.

Generated runtime state belongs in the active vault under `.lab/state/`; global config is limited to `~/.lab/vaults.toml`.
