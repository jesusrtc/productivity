# Core tests: unset LAB_WORKSPACE before running pytest

`LAB_WORKSPACE` exported in the interactive shell overrides the test fixtures'
`LAB_ROOT` (it wins in `paths.find_workspace_root`), silently pointing tests at
the real active workspace. Symptom: spurious failures in `test_term_routes.py`
/ `test_workspace_routes.py` / `test_frontend_logging.py` that vanish in CI.

Run tests as:

```bash
cd core && env -u LAB_WORKSPACE .venv/bin/python -m pytest -q
```

Also: `tests/test_watcher.py::test_watcher_rebuilds_on_project_creation` is a
real-`time.sleep` debounce test that flakes under load; rerun it standalone
before blaming a change.
