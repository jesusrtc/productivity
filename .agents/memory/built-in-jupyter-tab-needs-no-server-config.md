---
name: built-in-jupyter-tab-needs-no-server-config
description: Workspace Jupyter is first-class Lab UI; never point a servers.json proxy back at Lab's own port
metadata:
  type: workspace
---

Every workspace gets a built-in **Jupyter** top tab from Lab's notebook runtime.
It opens the last `.ipynb` for that workspace or a notebook launcher/create flow.
The launcher must identify the current workspace and path: notebook discovery is
workspace-scoped, so a notebook in one workspace must not silently appear in
another workspace's tab. An open notebook provides **All notebooks** to return to
that launcher.
Do not create a `servers.json` entry that points Jupyter at Lab's own port:
that is a self-proxy loop, and it would also split the intended human/agent
kernel workflow if replaced with an unrelated Jupyter process.
