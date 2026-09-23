# Dashboard reads overlap rendering after the file scan

Start dashboard reads from the sidebar's before-render callback after file data
arrives, then await the same request batch. Starting every request before the file
scan can congest Chrome's connection pool. Observe promise failures immediately
while rendering is pending, but report them only in the owning dashboard. A
dashboard generation guards old responses/errors, including revisits to the same
workspace and a document opened while the dashboard was loading.
