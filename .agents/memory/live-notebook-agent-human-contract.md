---
title: Live notebook agent/human contract
date: 2026-08-28
---

The target notebook experience is one shared kernel session per notebook for
humans and agents. An agent-created or modified cell must appear in the open UI
before/during execution with actor identity, running state, and elapsed time.
Jupyter IOPub text and rich outputs must stream into that cell as they arrive.
Humans must be able to edit/add/run/rerun cells and interrupt the active
execution. Agent execution does not require approval.

Keep the implementation small: Lab owns the kernel and notebook session; client
code is a custom Python library or IPython cell magic (for example `%%sql`) in
the configured runtime. Do not require the full JupyterLab UI, Docker, live
character-by-character co-editing, or a remote runner unless a later deployment
requires one.
