# Local servers in Lab

Only configure a server when the workspace needs one. The workspace owns its
implementation, dependencies, ports, and Makefile. Put Lab's server tabs and
proxies in workspace-root servers.json, not workspace.json:

```json
{
  "servers": [{
    "name": "app",
    "label": "Web app",
    "host": "127.0.0.1",
    "port": 5173,
    "path": "/",
    "mode": "proxy",
    "start_command": "make server-start",
    "stop_command": "make server-stop"
  }]
}
```

The name and port are required. Commands are optional but must be make
commands. The server modal rereads servers.json when opened or reloaded.

For Lab to supervise the process, define server-start in the workspace's
Makefile. It must run in the foreground. server-stop is optional. SERVER_PORT
and SERVER_HEALTH_URL tell Lab where to check health; use a cheap /healthz
endpoint when the application provides one. Select an available port.

```make
SERVER_PORT = 5173
SERVER_HEALTH_URL = http://127.0.0.1:5173/healthz

server-start:
	npm run dev -- --host 127.0.0.1 --port $(SERVER_PORT)
```

Inside Lab's proxy, locally authored HTML should include a base element with
target="_self" so links remain inside the proxy. Framework server URLs are
configurable: use `lab open` to open Lab; do not assume a fixed localhost port.
