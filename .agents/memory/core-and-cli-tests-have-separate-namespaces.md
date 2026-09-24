# Run core and CLI tests in separate pytest processes

Both `core/tests` and `core/cli/tests` are packages named `tests`. Combining their
paths in one ordinary pytest invocation raises `ImportPathMismatchError` while
loading the second `tests.conftest`, before tests execute. Run core and CLI
checks separately with the worktree's source paths. Do not count a failed
combined collection as executed coverage or change package imports merely to
combine these runs. Native Chrome tests also require the existing browser
execution permission; sandbox startup failures are separate from assertions.
