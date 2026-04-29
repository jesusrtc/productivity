# Testing Guidelines

## Test Location

Tests are located in `trustim-investigation/test/`. The test configuration is defined in
`trustim-investigation/setup.cfg`.

## Test Framework

- **pytest** with flags `-v -s` (verbose output, no stdout capture), configured in `setup.cfg` under `[tool:pytest]`
- **coverage** with branch coverage enabled; `show_missing = true`; excludes `pragma: nocover`,
  `raise NotImplementedError`, `raise AssertionError`

## Running Tests

Enter the virtual environment before running tests. Build and test via Gradle:

```bash
./gradlew build
```

This runs the full Python build pipeline including tests, flake8, mypy, and coverage.

To run pytest directly (after activating the venv):

```bash
cd trustim-investigation
pytest test/
```

After generating new tests, always run them to confirm they pass before submitting.

## Test Scope

The primary codebase is skill definitions (Markdown files) and a single Python CLI tool (`tools/davi_runner.py`). The
Python package under `trustim-investigation/src/` has minimal code (empty `__init__.py`). When adding Python
functionality, add corresponding tests in `trustim-investigation/test/`.

## Mocking Strategy

The `davi_runner.py` tool depends on external services (Darwin pods, Jupyter kernels, `lipy-darwin-local-client`). When
testing this tool:

- Mock `subprocess.Popen` and `subprocess.run` calls for process management (proxy, kernel startup, git clone)
- Mock `jupyter_client.BlockingKernelClient` for kernel communication
- Mock file I/O for PID files in `/tmp/davi-runner/` and connection files
- Mock `nbformat` read/write for notebook audit trail tests
- Use `unittest.mock.patch` to isolate external dependencies

## Type Checking

mypy is configured with strict settings in `setup.cfg` under `[mypy]`: `disallow_untyped_defs = true`,
`no_implicit_optional = true`, `strict_equality = true`, `warn_return_any = true`. All new Python code must include type
annotations.
