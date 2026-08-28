# Notebook tabs follow their owning workspace

A project tab may stay open while another workspace is globally active. Resolve
its `.ipynb` path relative to the project's catalog `workspace_path`, and carry
the owning workspace id on every notebook read, runtime, execute, delete,
restart, interrupt, live-replay, and WebSocket event. Key in-browser live-run
state by `(workspace id, notebook path)`, not by the relative path alone. A
direct `#/nb?path=projects/<id>/...` link with an explicit absolute `?project=`
must prefer that project over `LAB_WORKSPACE_ROOT`.
