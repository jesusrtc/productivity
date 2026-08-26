---
name: backend-python-changes-require-server-restart
description: The always-on Lab server serves static files from disk but keeps imported Python routes in memory, so backend source changes require a restart
metadata:
  type: project
---

The launch-agent / `make start` Lab server does not run Uvicorn hot reload.
Static JS/CSS changes appear after a browser reload, but Python route changes do
not take effect until `make restart`. This can temporarily pair a new frontend
with stale API behavior; compare the server process start time with the relevant
commit before diagnosing the route itself.
