# Project mtime polling is single-flight

- The one-second `/api/project-mtime` browser poll must never start while its previous request is still in flight. The endpoint performs a recursive filesystem walk guarded by a 10-second timeout, so overlapping interval callbacks can turn one slow scan into dozens of queued requests.
- Treat non-2xx responses as failures and retry with exponential backoff (capped at one minute). Reset the baseline and failure state when the active project changes, and ignore a response if it belongs to a project the user already left.
- Keep a Node regression that holds the first request open, fires a second timer tick, returns a 503, and verifies both single-flight behavior and delayed retry.
