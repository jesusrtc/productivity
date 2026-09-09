# lab

CLI for Lab vaults, workspaces, tasks, and the local server. See `../../docs/NAMING.md` for the entity model.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Subcommand overview (Plan 1)

- `lab workspace new|ls|status|set|archive|rm`
- `lab task new|ls|show|set|done|reopen|block|unblock`

Run `lab --help` for everything.
