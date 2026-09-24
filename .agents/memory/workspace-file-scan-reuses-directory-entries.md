# File scans reuse entries only within one request

`api_workspace_files` uses `os.scandir` type/stat data to avoid repeated filesystem
calls for each file. Keep entries request-local: later requests must see edits,
deletions, repaired/retargeted symlinks, and pending notebook state. Preserve
sorted traversal, depth resets, skip rules, and worktree checkout annotations.
`scripts/perf/lab_file_scan_latency.py` alternates a baseline implementation and
the candidate, checking full response equality without touching user workspaces.
