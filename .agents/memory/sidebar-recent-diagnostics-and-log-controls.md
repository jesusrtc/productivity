# Recent-file diagnostics and consolidated log controls

- After File sidebar settings are saved, the frontend writes a diagnostic summary to `frontend.log` and one event for each `README.md` returned by `/api/project-files` (up to 50). Each event includes the file path, mtime, age in minutes, and the exact inclusion or exclusion reason.
- Project-file fetch failures are logged explicitly, including the HTTP status, so a failed mtime scan is distinguishable from a file that falls outside the configured recent window.
- Productivity > Admin > Logs operates on the selected consolidated log. Copy copies the rendered log text; Flush confirms, then clears that log across registered workspace log directories through the admin-only `DELETE /api/log/clear/all` endpoint.
- Keep coverage in `test_frontend_sidebar_file_config.py`, `test_frontend_logging.py`, and `test_logging_infra.py` when changing this flow.
