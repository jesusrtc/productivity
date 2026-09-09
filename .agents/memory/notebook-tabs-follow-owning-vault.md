# Notebook tabs follow their owning vault

A workspace tab may stay open while another vault is globally active. Resolve
its `.ipynb` path relative to the workspace's catalog `vault_path`, and carry
the owning vault id on every notebook read, runtime, execute, delete,
restart, interrupt, live-replay, and WebSocket event. Key in-browser live-run
state by `(vault id, notebook path)`, not by the relative path alone. A
direct `#/nb?path=workspaces/<id>/...` link with an explicit absolute `?workspace=`
must prefer that workspace over `LAB_VAULT_ROOT`.
