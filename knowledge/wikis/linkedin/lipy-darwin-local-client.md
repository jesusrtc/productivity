---
title: "lipy-darwin-local-client"
date: 2026-04-02
type: wiki
scope: org
projects: []
tags: [darwin, jupyter, local-dev, setup-guide]
sources: ["lipy-darwin-local-client/README.md (GitHub Pages)", "lipy-darwin-local-client/ARCHITECTURE.md (GitHub Pages)"]
---

# lipy-darwin-local-client

Darwin is LinkedIn's managed Jupyter notebook environment with access to production clusters, HDFS, PySpark, Scala Spark, and Trino/SQL — powerful, but web-based. That means limited IDE support, few AI coding tools, and no Claude/Cursor/Windsurf extensions.

This library bridges your local environment to Darwin so you can write and iterate on code with every local tool you have, then execute it on production-grade Darwin clusters.

**Your local AI tools. Darwin's compute. No compromises.**

## Setup

### Option A — Inside an existing MP

Best if you want to run notebooks in your own MP's environment.

```bash
source activate                          # activate your MP's venv
python -m pip install \
  --index-url https://lerna.tools.corp.linkedin.com/pypi/simple \
  lipy-darwin-local-client
jupyter-proxy                            # fetches auth token automatically
```

Then open a notebook and select your MP's venv as the kernel.

### Option B — Standalone environment

Best for rapid experimentation or agentic workflows outside an MP.

```bash
mint clone lipy-darwin-local-client
cd lipy-darwin-local-client
mint run                                 # creates .venv
.venv/bin/jupyter-proxy                 # fetches auth token automatically
```

Then open `notebooks/quick-starts/pyspark_notebook.ipynb` and select `.venv/bin/python` as the kernel.

### Option C — Linux box

```bash
python3 -m ensurepip --upgrade
python3 -m pip install uv

sudo --preserve-env=PATH sh -c \
"mkdir -p /etc/lipki && \
trust-ca-tool create-trust-cfg \
  --target-pem /etc/lipki/public-ca.crt \
  --target-jks /etc/lipki/public-cacerts \
  --trust-ca-category public \
  -CF LINKEDIN_CA | \
trust-ca-tool create-truststore -f - && \
update-ca-trust"

export SSL_CERT_FILE=/etc/lipki/ca-bundle.crt

mint clone lipy-darwin-local-client
cd lipy-darwin-local-client
mint run
.venv/bin/jupyter-proxy
```

## First Cells

```python
%load_ext linkedin.darwinlocalclient.kernel_magic
%remote --connect --new    # auto-starts Darwin pod if needed
```

## Typical Notebook Setup

```python
# Terminal: .venv/bin/jupyter-proxy  ← auto-fetches token, auto-starts pod, kills existing instance

%load_ext linkedin.darwinlocalclient.kernel_magic
%remote --connect --new        # defaults to http://localhost:8889; creates fresh kernel
%remote --default spark        # plain cells run on Spark by default

from linkedin.darwinlocalclient.bundler import bundle_file, execute_file
execute_file("/path/to/my_spark_job.py", args=["input_path", "output_path"])
```

## Main API

```python
from linkedin.darwinlocalclient.bundler import bundle_file, execute_file, show_lines, invalidate_cache
```

## Darwin Infrastructure Notes

- **Pod spawning**: `GET /k8s/hub/login` with `DVToken` header + `darwin_dv_token_session` cookie + `userOptions` JSON header. NOT the standard JupyterHub API.
- **Pod state check**: `GET /user/{username}/api/status` against `darwin.prod.linkedin.com`. Status codes: 200=running, 404/500=not_running, 503=starting, 502=unhealthy, 504=being_culled.
- **Two auth cookie names**: `darwin-play-session` for Jupyter Server (CHP), `darwin_dv_token_session` for Hub login. Wrong one silently fails.
- **Pod status check requires BOTH** `DVToken` header AND `darwin-play-session` cookie.
- **Proxy scope**: `jupyter-proxy` only covers `https://darwin.prod.linkedin.com/user/{USERNAME}/`. Pod lifecycle calls go directly to Darwin.
- **Proxy auth self-healing**: on 401/403, runs `authn-cli` in background, updates `DVTOKEN` in memory, retries once. Gives up after 3 consecutive failures (resets after 5-min cooldown).
- **Proxy pod self-healing**: on 405 (pod timeout), calls `ensure_pod_running()` once and retries.
- **WS reconnect self-healing**: HTTP ping to `/api/kernels/{id}` before each WS attempt triggers auth self-heal.
- **PID file**: `~/.darwin/jupyter-proxy-{PORT}.pid` — keyed by port so multiple instances can coexist.
- **`proxyUser` in `%%spark config`**: optional, omit by default. If present with placeholder, Spark submission fails.

## Related Repos (Darwin Ecosystem)

| Repo | What to look at |
|------|-----------------|
| `lipy-darwin-mcp` | **Start here for Darwin API work.** pod lifecycle, config, file ops, auth, kernel management |
| `darwin-cli` | Real usage examples of every Darwin operation; persistent kernel session pattern |
| `li-jupyter-server` | Darwin-custom endpoints, GPU kernel pod management (k8s), DVToken auth server-side |
| `lipy-darwin-mcp-common` | Server-side MCP infrastructure only (auth middleware, uvicorn controller) |
| `darwin-mcp-service` | MCP tool servers for Spark logs and Trino queries |

## Support

Slack: #darwin-local-client
