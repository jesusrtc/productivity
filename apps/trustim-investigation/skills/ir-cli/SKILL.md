---
name: ir-cli
description: >-
  Reference for the trustim-ir-cli tool (`ir`), a CLI for InResponse (airp-web).
  Covers alert, incident, comment, and timeline management from the terminal.
  Use when the user wants to manage IR alerts/incidents via CLI or needs to understand
  the airp-web HTML API endpoints.
allowed-tools: Bash, Read, Glob
---

# IR CLI (trustim-ir-cli)

`ir` is a CLI tool for InResponse (airp-web) that provides subcommands for managing alerts, incidents, comments, and timelines.

**Repo:** `linkedin-multiproduct/trustim-ir-cli`

## Before using this skill

Clone the repo (if not already cloned) and read its docs for the latest usage details:

```bash
# Clone to a temp directory, or pull latest if already cached
IR_CLI_DIR="/tmp/trustim-ir-cli"
if [ -d "$IR_CLI_DIR" ]; then
  cd "$IR_CLI_DIR" && git checkout master && git pull
else
  gh repo clone linkedin-multiproduct/trustim-ir-cli "$IR_CLI_DIR"
fi
```

Refer to `$IR_CLI_DIR/trustim-ir-cli/README.md` for CLI usage, authentication, environment config, and command reference.

Refer to `$IR_CLI_DIR/CLAUDE.md` for project structure and development patterns.

## Key things to know

- Deploying a new version of airp-web kills existing sessions — re-run `ir auth login --no-validate` after deploys.
- Auth cookies are stored per-environment (stg/prod) in `~/.config/ir/config.toml`.
- mTLS is handled automatically via macOS keychain; use `ir config --list-certs` to verify.
