# Live notebook streaming requires Lab's executor

Directly editing a `.ipynb` and then executing it with Jupyter, ipykernel,
nbclient, or nbconvert bypasses Lab's notebook event publisher. The open UI
cannot infer the actor, start time, elapsed time, or partial outputs and will
only notice the completed file.

Agents must use `lab notebook exec <path> --code ...` (or `--cell-id ...
--file ...`). This routes execution through `POST /api/nb/exec`, which records
the running metadata before kernel dispatch and broadcasts incremental output
to every open notebook view.
