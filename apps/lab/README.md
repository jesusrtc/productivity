# lab

Unified CLI for the productivity monorepo. See `../../docs/superpowers/specs/2026-04-16-productivity-monorepo-design.md` for the design.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Subcommand overview (Plan 1)

- `lab project new|ls|status|set|archive|rm`
- `lab task new|ls|show|set|done|reopen|block|unblock`

Run `lab --help` for everything.
