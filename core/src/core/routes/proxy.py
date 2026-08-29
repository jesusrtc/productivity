"""Per-project reverse-proxy for local dev servers.

A project can declare one or more servers in its root `servers.json`:

    {"servers": [
      {
        "name": "frontend", "host": "localhost", "port": 3000, "path": "/",
        "start_command": "make server-start", "stop_command": "make server-stop"
      },
      {"name": "api",      "port": 8000,        "path": "/docs"}
    ]}

Legacy `project.json.proxies` declarations remain readable when there is no
`servers.json`; saving from the Servers modal creates the standalone file.

…and the lab server exposes each at:

    HTTP : /api/workspace-proxy/<workspace>/<project_id>/<name>/<path>
    WS   : /ws/workspace-proxy/<workspace>/<project_id>/<name>/<path>

The older unscoped ``/api/proxy`` and ``/ws/proxy`` mounts remain available
for bookmarks created before Lab supported simultaneous cross-workspace tabs.

so the frontend can mount the dev server inside an iframe alongside the
project's terminal + notebooks, without the browser needing direct access
to the target port. The lab server is the only network endpoint the user
needs to reach.

Notes & limitations:

* Only ports explicitly declared in `servers.json` (or legacy
  `project.json.proxies`) are reachable — there
  is no open-ended `/proxy/foo/<arbitrary-host-and-port>` path. This is
  also why apps that hardcode absolute paths (e.g. `/static/foo.js`) need
  to be configured to run under a base path, OR rely on the
  `<base href>` we inject below into HTML responses. For React/Vite/Next
  apps, set the framework's basePath/base option to the same value as
  the proxy's mount path.
* Hop-by-hop headers (`connection`, `transfer-encoding`, …) are
  stripped per RFC 7230 §6.1.
* `Set-Cookie` headers have their name prefixed with
  ``lp_<project>_<name>__`` and their Path scoped to the proxy mount,
  so cookies from two different proxied apps with the same cookie name
  don't collide on the lab origin.
* WebSocket upgrade is forwarded bidirectionally so HMR / live-reload
  works (Vite, Next.js dev server, etc.).
* Optional ``start_command`` / ``stop_command`` values must be ``make``
  commands. They run from the project directory through explicit control
  endpoints; the start command is hosted in tmux so foreground dev servers
  remain alive after the request returns.
* If the target port isn't listening, the HTTP endpoint returns a
  502-styled placeholder page ("dev server not running") instead of an
  opaque connection error.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.requests import ClientDisconnect

from lab import tmux_sockets

from core import auth, server_config
from core.routes import term as term_routes


router = APIRouter()
log = logging.getLogger("core.proxy")


# Hop-by-hop headers that should not be forwarded across a proxy hop.
# Lowercased for case-insensitive comparison.
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    # Stripped because httpx already decoded the body for us — leaving
    # this header in the response would cause the browser to try to
    # re-decode an already-decoded payload.
    "content-encoding",
    "content-length",
    # We rewrite/set this ourselves.
    "host",
}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _incoming_port(conn: Request | WebSocket) -> int | None:
    url = getattr(conn, "url", None)
    if url is not None and url.port:
        return int(url.port)
    server = conn.scope.get("server")
    if server and len(server) >= 2 and server[1]:
        return int(server[1])
    scheme = conn.scope.get("scheme")
    if scheme in {"http", "ws"}:
        return 80
    if scheme in {"https", "wss"}:
        return 443
    return None


def _is_self_proxy(cfg: dict[str, Any], conn: Request | WebSocket) -> bool:
    if int(cfg.get("port") or 0) != _incoming_port(conn):
        return False
    host = str(cfg.get("host") or "").strip().lower().strip("[]")
    if host in _LOCAL_HOSTS:
        return True
    url_host = getattr(getattr(conn, "url", None), "hostname", None)
    if url_host and host == url_host.lower().strip("[]"):
        return True
    server = conn.scope.get("server")
    return bool(server and server[0] and host == str(server[0]).lower().strip("[]"))


def _self_proxy_response(project_id: str, name: str, cfg: dict[str, Any]) -> Response:
    html = (
        "<!doctype html><html><body style=\"font-family:ui-monospace,monospace;"
        "background:#0d1117;color:#c9d1d9;padding:32px;line-height:1.5\">"
        "<h2 style=\"color:#f78166;margin-top:0\">Proxy points at Lab itself</h2>"
        f"<p>Proxy <b>{name}</b> in project <b>{project_id}</b> targets "
        f"<code>{cfg['host']}:{cfg['port']}</code>, which is this Lab server.</p>"
        "<p style=\"color:#8b949e\">Change the proxy port to your dev server port "
        "or remove the proxy entry.</p>"
        "</body></html>"
    )
    return Response(
        content=html.encode("utf-8"),
        status_code=409,
        media_type="text/html; charset=utf-8",
    )


def _project_dir(root: Path, project_id: str) -> Path:
    """Map a project id to its `projects/<id>/` folder."""
    return root / "projects" / project_id


def _existing_project_dir(root: Path, project_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", project_id) or project_id in {".", ".."}:
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    project_dir = _project_dir(root, project_id)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
    return project_dir


def _read_server_config(root: Path, project_id: str) -> tuple[list[dict[str, Any]], str]:
    project_dir = _existing_project_dir(root, project_id)
    try:
        return server_config.read_server_config(project_dir)
    except server_config.ServerConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _load_proxy_config(
    root: Path,
    project_id: str,
    name: str,
    *,
    suppress_errors: bool = False,
) -> dict[str, Any] | None:
    """Look up the named server in `servers.json` or legacy project metadata.

    Returns a dict with `host` (default ``localhost``), `port`, and
    `path` (default ``/``) — or None when the project doesn't exist or
    has no proxy by that name.
    """
    try:
        proxies, _source = _read_server_config(root, project_id)
    except HTTPException:
        if suppress_errors:
            return None
        raise
    for entry in proxies:
        if entry.get("name") != name:
            continue
        return entry
    return None


def _list_proxies(root: Path, project_id: str) -> list[dict[str, Any]]:
    """Return all configured proxies for a project (or empty list)."""
    try:
        proxies, _source = _read_server_config(root, project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return []
        raise
    return proxies


def _parse_make_command(raw: str, field: str) -> list[str]:
    """Parse one configured control command without enabling shell syntax."""
    command = (raw or "").strip()
    if not command:
        raise HTTPException(status_code=409, detail=f"proxy has no {field} configured")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid {field}: {exc}") from None
    if not argv or argv[0] != "make":
        raise HTTPException(status_code=400, detail=f"{field} must be a make command")
    return argv


def _proxy_control_session_name(root: Path, project_id: str, name: str) -> str:
    return term_routes._tmux_name_for(project_id, f"server-{name}", root)


def _run_make_command(argv: list[str], project_dir: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=20,
            env=term_routes._tmux_child_env(),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"{' '.join(argv)} timed out after 20s") from None


def _command_failure(proc: subprocess.CompletedProcess[str], fallback: str) -> str:
    return (proc.stderr or proc.stdout or fallback).strip()[:1000]


def _kill_proxy_control_session(session_name: str) -> None:
    if not term_routes._tmux_available():
        return
    socket_name = (
        term_routes._tmux_find_session_socket(session_name)
        or tmux_sockets.DEFAULT_SOCKET
    )
    subprocess.run(
        term_routes._tmux_command(
            socket_name,
            "kill-session",
            "-t",
            session_name,
        ),
        capture_output=True,
        text=True,
        env=term_routes._tmux_child_env(),
    )


def _start_proxy_server(root: Path, project_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    start_argv = _parse_make_command(cfg.get("start_command", ""), "start command")
    if not term_routes._tmux_available():
        raise HTTPException(status_code=500, detail="tmux not installed. Run: brew install tmux")
    project_dir = _project_dir(root, project_id)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")

    session_name = _proxy_control_session_name(root, project_id, cfg["name"])
    was_running = term_routes._tmux_has_session(session_name)
    if was_running:
        stop_raw = str(cfg.get("stop_command") or "").strip()
        if stop_raw:
            stop_proc = _run_make_command(_parse_make_command(stop_raw, "stop command"), project_dir)
            if stop_proc.returncode != 0:
                raise HTTPException(
                    status_code=409,
                    detail=_command_failure(stop_proc, "stop command failed before restart"),
                )
        _kill_proxy_control_session(session_name)

    command = shlex.join(start_argv)
    with tmux_sockets.state_lock():
        socket_name = term_routes._active_tmux_socket()
        if (
            socket_name != tmux_sockets.DEFAULT_SOCKET
            and not term_routes._tmux_server_alive(socket_name)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"terminal socket {socket_name!r} is no longer running; "
                    "run `lab terminal rotate` directly from iTerm"
                ),
            )
        proc = subprocess.run(
            term_routes._tmux_command(
                socket_name,
                "new-session",
                "-d",
                "-s",
                session_name,
                "-c",
                str(project_dir),
                command,
            ),
            capture_output=True,
            text=True,
            env=term_routes._tmux_child_env(),
        )
    if proc.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail=_command_failure(proc, "tmux could not start the server command"),
        )
    return {
        "ok": True,
        "action": "restarted" if was_running else "started",
        "session_name": session_name,
    }


def _stop_proxy_server(root: Path, project_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    project_dir = _project_dir(root, project_id)
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")

    stop_argv = _parse_make_command(cfg.get("stop_command", ""), "stop command")
    session_name = _proxy_control_session_name(root, project_id, cfg["name"])
    proc = _run_make_command(stop_argv, project_dir)
    _kill_proxy_control_session(session_name)
    if proc.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail=_command_failure(proc, "stop command failed"),
        )
    return {"ok": True, "action": "stopped", "session_name": session_name}


# Inject this between `<head>` and the rest of the document so relative
# URLs in the proxied app resolve under our mount path. Absolute paths
# (`/static/foo.js`) still escape — apps that need absolute paths must
# configure a base path in their framework (Vite `base`, Next.js
# `basePath`, etc.).
_HEAD_RE = re.compile(rb"(<head[^>]*>)", re.IGNORECASE)


def _inject_base_href(body: bytes, base_href: str) -> bytes:
    """Inject a `<base href=…>` tag as the first child of `<head>`.

    Idempotent: if a `<base ` tag already exists we leave the document
    alone (the upstream app already declared one and we'd otherwise
    fight it).
    """
    if not body:
        return body
    # Cheap pre-check before parsing.
    if b"<base " in body[:4096].lower() or b"<BASE " in body[:4096]:
        return body
    tag = f'<base href="{base_href}">'.encode("utf-8")
    new_body, n = _HEAD_RE.subn(rb"\1" + tag, body, count=1)
    if n == 0:
        # No `<head>` — just prepend the base tag. Browsers tolerate it
        # outside <head> in quirks-mode, which is fine for bare HTML
        # demos.
        return tag + body
    return new_body


def _rewrite_cookie(cookie: str, name_prefix: str, mount_path: str) -> str:
    """Prefix the cookie name and scope it to the proxy mount path.

    Removes any `Domain=` attribute the upstream sent (which would name
    a domain the browser doesn't recognise since we're on the lab
    origin) and replaces `Path=` with our mount path so two proxied
    apps with the same cookie name (e.g. `session`) don't collide.
    """
    parts = [p.strip() for p in cookie.split(";") if p.strip()]
    if not parts:
        return cookie
    head = parts[0]
    if "=" in head:
        name, _, value = head.partition("=")
        head = f"{name_prefix}{name.strip()}={value}"
    out = [head]
    for attr in parts[1:]:
        low = attr.lower()
        if low.startswith("domain="):
            continue
        if low.startswith("path="):
            continue
        out.append(attr)
    out.append(f"Path={mount_path}")
    return "; ".join(out)


class ServerConfigBody(BaseModel):
    servers: list[dict[str, Any]]


def _workspace_root(request: Request | WebSocket, workspace: str | None) -> Path:
    active_root = auth.request_root(request)
    root = term_routes._workspace_root_for(active_root, workspace)
    auth.require_workspace(request, term_routes._workspace_id_for_root(active_root, root))
    return root


@router.get("/api/server-config")
def get_server_config(
    request: Request, project_id: str, workspace: str | None = None,
) -> dict[str, Any]:
    """Return the effective configuration and the file it came from."""
    root = _workspace_root(request, workspace)
    servers, source = _read_server_config(root, project_id)
    return {
        "servers": servers,
        "source": source,
        "config_file": server_config.CONFIG_FILENAME,
        "is_legacy": source in {"project.json", ".project.json"},
    }


@router.put("/api/server-config")
def put_server_config(
    body: ServerConfigBody,
    request: Request,
    project_id: str,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Write the canonical ``servers.json`` for a project."""
    root = _workspace_root(request, workspace)
    project_dir = _existing_project_dir(root, project_id)
    try:
        servers = server_config.write_server_config(project_dir, body.servers)
    except server_config.ServerConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write servers.json: {exc}") from None
    return {
        "ok": True,
        "servers": servers,
        "source": server_config.CONFIG_FILENAME,
        "config_file": server_config.CONFIG_FILENAME,
        "is_legacy": False,
    }


@router.get("/api/proxies")
def list_proxies(
    request: Request, project_id: str, workspace: str | None = None,
) -> list[dict[str, Any]]:
    """List the effective servers declared for a project.

    Drives the sidebar 'Servers' section in the frontend.
    """
    root = _workspace_root(request, workspace)
    return _list_proxies(root, project_id)


@router.post("/api/proxies/{project_id}/{name}/{action}")
def control_proxy_server(
    project_id: str,
    name: str,
    action: str,
    request: Request,
    workspace: str | None = None,
) -> dict[str, Any]:
    """Run a configured make command from the owning project directory."""
    if action not in {"start", "restart", "stop"}:
        raise HTTPException(status_code=404, detail=f"unknown proxy action {action!r}")
    root = _workspace_root(request, workspace)
    cfg = _load_proxy_config(root, project_id, name)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail=f"proxy {name!r} not declared in project {project_id!r}",
        )
    if action == "stop":
        return _stop_proxy_server(root, project_id, cfg)
    return _start_proxy_server(root, project_id, cfg)


def _proxy_mount_path(workspace: str | None, project_id: str, name: str) -> str:
    if workspace:
        return "/api/workspace-proxy/{}/{}/{}/".format(
            quote(workspace, safe=""), quote(project_id, safe=""), quote(name, safe=""),
        )
    return "/api/proxy/{}/{}/".format(
        quote(project_id, safe=""), quote(name, safe=""),
    )


@router.api_route(
    "/api/workspace-proxy/{workspace}/{project_id}/{name}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
@router.api_route(
    "/api/proxy/{project_id}/{name}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_http(
    project_id: str,
    name: str,
    path: str,
    request: Request,
    workspace: str | None = None,
):
    root = _workspace_root(request, workspace)
    cfg = _load_proxy_config(root, project_id, name)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail=f"proxy {name!r} not declared in project {project_id!r}",
        )
    if cfg["port"] <= 0:
        raise HTTPException(
            status_code=500,
            detail=f"proxy {name!r} has no port configured",
        )
    if _is_self_proxy(cfg, request):
        return _self_proxy_response(project_id, name, cfg)

    upstream = f"http://{cfg['host']}:{cfg['port']}/{path}"
    if request.url.query:
        upstream += "?" + request.url.query

    # Forward headers, stripping hop-by-hop, and overriding Host so the
    # upstream sees a request that looks like it came from a local
    # browser, not the lab server.
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP
    }
    headers["host"] = f"{cfg['host']}:{cfg['port']}"

    try:
        body = await request.body()
    except ClientDisconnect:
        return Response(status_code=499)

    try:
        timeout = httpx.Timeout(30.0, connect=1.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            upstream_resp = await client.request(
                request.method, upstream, headers=headers, content=body,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # Friendly placeholder when the dev server isn't running yet.
        request.state.log_level_override = logging.WARNING
        html = (
            f"<!doctype html><html><body style=\"font-family:ui-monospace,monospace;"
            f"background:#0d1117;color:#c9d1d9;padding:32px;line-height:1.5\">"
            f"<h2 style=\"color:#f78166;margin-top:0\">Dev server not reachable</h2>"
            f"<p>Could not connect to <code>{cfg['host']}:{cfg['port']}</code> "
            f"(proxy <b>{name}</b> in project <b>{project_id}</b>).</p>"
            f"<p style=\"color:#8b949e\">Start your dev server, then reload this view.</p>"
            f"</body></html>"
        )
        return Response(
            content=html.encode("utf-8"),
            status_code=502,
            media_type="text/html; charset=utf-8",
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"proxy error: {e!s}") from None

    out_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in HOP_BY_HOP
    }
    # We re-handle Set-Cookie below.
    out_headers.pop("set-cookie", None)

    # Inject <base href> into HTML so relative links and asset paths
    # land back at our mount point instead of the lab origin root.
    mount = _proxy_mount_path(workspace, project_id, name)
    content = upstream_resp.content
    media = upstream_resp.headers.get("content-type", "")
    if media.lower().startswith("text/html"):
        content = _inject_base_href(content, mount)

    resp = Response(
        content=content, status_code=upstream_resp.status_code, headers=out_headers,
    )

    # Re-attach Set-Cookie with a per-proxy name prefix + Path scoped to
    # the mount, so cookies from two proxied apps with the same name
    # don't clobber each other on the lab origin.
    cookie_workspace = re.sub(r"[^A-Za-z0-9_-]", "_", workspace) if workspace else ""
    cookie_scope = f"{cookie_workspace}_" if cookie_workspace else ""
    cookie_prefix = f"lp_{cookie_scope}{project_id}_{name}__"
    raw_cookies = upstream_resp.headers.get_list("set-cookie") \
        if hasattr(upstream_resp.headers, "get_list") else []
    if not raw_cookies and "set-cookie" in upstream_resp.headers:
        raw_cookies = [upstream_resp.headers["set-cookie"]]
    for c in raw_cookies:
        if not c:
            continue
        resp.raw_headers.append(
            (b"set-cookie", _rewrite_cookie(c, cookie_prefix, mount.rstrip("/")).encode("utf-8")),
        )

    return resp


@router.websocket("/ws/workspace-proxy/{workspace}/{project_id}/{name}/{path:path}")
@router.websocket("/ws/proxy/{project_id}/{name}/{path:path}")
async def proxy_ws(
    websocket: WebSocket,
    project_id: str,
    name: str,
    path: str,
    workspace: str | None = None,
):
    """Bidirectional WebSocket proxy.

    Drives HMR / live-reload for Vite, Next.js, Webpack dev server, etc.
    Closes both sides on either end disconnecting.
    """
    try:
        root = _workspace_root(websocket, workspace)
    except HTTPException as exc:
        await websocket.close(code=4401 if exc.status_code == 401 else 4403)
        return
    cfg = _load_proxy_config(root, project_id, name, suppress_errors=True)
    path_info = (
        f"/ws/workspace-proxy/{workspace}/{project_id}/{name}/{path}"
        if workspace else f"/ws/proxy/{project_id}/{name}/{path}"
    )
    if cfg is None or cfg["port"] <= 0:
        log.warning(
            "WS proxy %s not configured",
            path_info,
            extra={"path_info": path_info, "event_type": "ws.reject"},
        )
        # 4404 is in the application close-code range (4000-4999), used
        # here as "not configured".
        await websocket.close(code=4404)
        return
    if _is_self_proxy(cfg, websocket):
        log.warning(
            "WS proxy %s points at lab itself",
            path_info,
            extra={"path_info": path_info, "event_type": "ws.self_proxy"},
        )
        await websocket.close(code=4409)
        return

    await websocket.accept()
    log.info(
        "WS proxy %s connected",
        path_info,
        extra={"path_info": path_info, "event_type": "ws.connect"},
    )

    upstream_url = f"ws://{cfg['host']}:{cfg['port']}/{path}"
    qs = websocket.scope.get("query_string", b"").decode()
    if qs:
        upstream_url += "?" + qs

    # Forward selected request headers (Origin, Cookie, Sec-WebSocket-Protocol)
    # so the upstream sees a request that looks browser-originated.
    forwarded_headers: dict[str, str] = {}
    for k in ("cookie", "origin", "sec-websocket-protocol", "user-agent"):
        v = websocket.headers.get(k)
        if v:
            forwarded_headers[k] = v

    try:
        async with websockets.connect(
            upstream_url,
            additional_headers=forwarded_headers,
            open_timeout=10,
            max_size=None,
        ) as upstream:
            async def client_to_upstream() -> None:
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            await upstream.close()
                            return
                        if "text" in msg and msg["text"] is not None:
                            await upstream.send(msg["text"])
                        elif "bytes" in msg and msg["bytes"] is not None:
                            await upstream.send(msg["bytes"])
                except (WebSocketDisconnect, websockets.ConnectionClosed):
                    pass

            async def upstream_to_client() -> None:
                try:
                    async for msg in upstream:
                        if isinstance(msg, (bytes, bytearray)):
                            await websocket.send_bytes(bytes(msg))
                        else:
                            await websocket.send_text(str(msg))
                except (WebSocketDisconnect, websockets.ConnectionClosed):
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except (OSError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
        log.error(
            "WS proxy %s upstream failed: %s",
            path_info,
            e,
            extra={"path_info": path_info, "event_type": "ws.error"},
        )
        try:
            await websocket.close(code=1011, reason=f"upstream: {e!s}"[:120])
        except Exception:
            pass
    except Exception:
        log.exception(
            "WS proxy %s failed",
            path_info,
            extra={"path_info": path_info, "event_type": "ws.error"},
        )
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    else:
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        log.info(
            "WS proxy %s disconnected",
            path_info,
            extra={"path_info": path_info, "event_type": "ws.disconnect"},
        )
