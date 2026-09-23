# Dashboard read coordination (earlier checkpoint)

The cold-path scheduling below was superseded by
[starting reads after file dispatch](cold-dashboard-reads-follow-file-dispatch.md).
The one-batch, error-observation and ownership rules still apply.

The earlier implementation started reads from the before-render callback after file data
arrived, then awaited the same request batch. Starting every request before the file
scan can congest Chrome's connection pool. Observe promise failures immediately
while rendering is pending, but report them only in the owning dashboard. A
dashboard generation guards old responses/errors, including revisits to the same
workspace and a document opened while the dashboard was loading.
