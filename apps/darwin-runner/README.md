# darwin-runner

Thin wrapper around Darwin notebook execution — the `davi_runner.py` CLI. Use for matplotlib charts produced from Trino queries.

## Usage

```
./darwin-runner run-local --notebook <name>
./darwin-runner run-remote --notebook <name>
./darwin-runner ls
```

Installed to `~/.local/bin/darwin-runner` via `make install` at the monorepo root.
