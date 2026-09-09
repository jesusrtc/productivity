# Naming refactor validation

## Contract

- Vault is the registered storage root; Workspace is the persistent work area; Terminal is the user-facing terminal container.
- UI copy, DOM IDs, CSS selectors, JS/Python identifiers, module filenames, CLI, HTTP contracts, new configuration, tests, documentation, and agent instructions use those names.
- Existing physical paths stay stable so notebooks, Git worktrees, linked files, and running terminals keep their identities.
- Compatibility readers translate both old entity names together and preserve account grants, IDs, paths, command strings, and user-authored text.
- Claude/Copilot formats and Python package metadata retain their native names.

## Verification

- `make test`: 204 CLI tests and 652 backend tests passed; 11 slow checks excluded by the standard target.
- Follow-up notebook and legacy-data checks: 8 CLI tests passed. Follow-up vault, Assistant, shared-file, and browser-migration checks: 30 backend tests passed. The final compatibility module adds coverage for repository discovery through the legacy environment variable.
- Python compilation, syntax checks for all 15 JavaScript files, `git diff --check`, and repo-local memory-link checks passed.
- The new CLI recognizes the existing Local and SSD vault registry entries and discovers Local workspaces at their existing paths.
- After restart, the live public health endpoint, canonical JS/CSS assets, browser-migration asset, and old-link redirect passed HTTP checks.
- UI behavior is exercised by Node-driven frontend tests. Direct visual inspection was unavailable because the computer-control service could not access a browser window. No privileged live data was read for HTTP verification.

The expanded staged suite passed 659 checks and failed three latency budgets. An unchanged-checkout comparison also failed those budgets (four of five latency checks failed there). The thresholds were left unchanged; these machine-dependent timing failures are separate from the passing standard test target.

See [Naming and compatibility](NAMING.md) for the public names and legacy data contracts.
