---
name: built-in-jupyter-tab-needs-no-server-config
description: Project Jupyter is first-class Lab UI; never point a servers.json proxy back at Lab's own port
metadata:
  type: project
---

Every project gets a built-in **Jupyter** top tab from Lab's notebook runtime.
It opens the last `.ipynb` for that project or a notebook launcher/create flow.
The launcher must identify the current project and path: notebook discovery is
project-scoped, so a notebook in one project must not silently appear in
another project's tab. An open notebook provides **All notebooks** to return to
that launcher.
Do not create a `servers.json` entry that points Jupyter at Lab's own port:
that is a self-proxy loop, and it would also split the intended human/agent
kernel workflow if replaced with an unrelated Jupyter process.
