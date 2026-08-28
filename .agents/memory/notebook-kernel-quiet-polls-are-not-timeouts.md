# Quiet Jupyter polls are not execution timeouts

A notebook cell that calls a client CLI, database, or subprocess may produce no
IOPub messages for many seconds or minutes. `jupyter_client` raising
`queue.Empty` from a short `get_iopub_msg(timeout=...)` poll means only that the
poll was quiet. Continue polling and enforce the cell's configured overall
monotonic deadline; do not convert the first empty poll into a 504.
