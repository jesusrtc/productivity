# Core tests: unset LAB_VAULT before running pytest

`LAB_VAULT` exported in the interactive shell overrides the test fixtures'
`LAB_ROOT` (it wins in `paths.find_vault_root`), silently pointing tests at
the real active vault. Symptom: spurious failures in `test_term_routes.py`
/ `test_vault_routes.py` / `test_frontend_logging.py` that vanish in CI.

Run tests as:

```bash
cd core && env -u LAB_VAULT -u LAB_WORKSPACE .venv/bin/python -m pytest -q
```

Also: `tests/test_watcher.py::test_watcher_rebuilds_on_workspace_creation` is a
real-`time.sleep` debounce test that flakes under load; rerun it standalone
before blaming a change.
