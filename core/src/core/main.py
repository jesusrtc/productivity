from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import config
from lab import paths as lab_paths
from core.routes import appstate as appstate_route
from core.routes import cerebro as cerebro_route
from core.routes import code_search as code_search_route
from core.routes import diff as diff_route
from core.routes import git as git_route
from core.routes import index as index_route
from core.routes import log as log_route
from core.routes import markdown as markdown_route
from core.routes import mutation as mutation_route
from core.routes import nb_exec as nb_exec_route
from core.routes import notebook as notebook_route
from core.routes import project as project_route
from core.routes import proxy as proxy_route
from core.routes import search as search_route
from core.routes import servers as servers_route
from core.routes import settings as settings_route
from core.routes import task as task_route
from core.routes import term as term_route
from core.routes import ui as ui_route
from core.routes import workspace as workspace_route
from core.routes import ws as ws_route
from core.state import IndexCache, IndexUpdatedEvent, WsBroadcaster
from core.watcher import IndexWatcher


# ─── Structured file logging ─────────────────────────────────────────────────
# Single JSON-lines formatter used by the file handlers attached to the root
# logger during lifespan startup.  Console output is unchanged.

class _JsonFormatter(logging.Formatter):
    """Newline-delimited JSON log entries for the app's three log files.

    Fields: ts, level, logger, source, msg, path, exc (if any), session_id (if any).
    Server entries derive ``path`` from the LogRecord's filename:lineno.
    Client entries (from routes/log.py) carry ``source="client"`` and
    ``path_info`` via the ``extra`` dict; the formatter routes them correctly.
    """

    _optional_fields = (
        "method",
        "route",
        "status_code",
        "duration_ms",
        "client",
        "action",
        "target",
        "event_type",
        "href",
        "source_url",
    )

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        )
        source = getattr(record, "source", "server")
        path_info = getattr(record, "path_info", None)
        if path_info is not None:
            path = path_info
        elif source == "client":
            path = ""
        else:
            path = f"{record.filename}:{record.lineno}"

        entry: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "source": source,
            "msg": record.getMessage(),
            "path": path,
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        sid = getattr(record, "session_id", None)
        if sid is not None:
            entry["session_id"] = sid
        for field in self._optional_fields:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        return json.dumps(entry, ensure_ascii=False)

# Keep module-level references so lifespan can remove them on shutdown.
_log_file_handlers: list[logging.Handler] = []


def _detach_file_logging() -> None:
    """Remove and close Lab's workspace-local file handlers."""
    root_logger = logging.getLogger()
    for h in _log_file_handlers:
        root_logger.removeHandler(h)
        h.close()
    _log_file_handlers.clear()


def _attach_file_logging(root: Path) -> Path:
    """Attach split JSONL file handlers for one active workspace."""
    _detach_file_logging()
    log_dir = lab_paths.logs_dir(root)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Split files. The root logger's effective level needs to allow INFO
    # through so the info-level split handlers see anything at all, but each
    # handler's level/filter still does the routing.
    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)

    def _make(name: str, level: int, flt) -> logging.Handler:
        # Rotate at 50MB with two backups per file: the UI polls several
        # endpoints every few seconds and each request logs a line, so an
        # unbounded FileHandler grew these files past 1GB within a week.
        handler = logging.handlers.RotatingFileHandler(
            log_dir / name, maxBytes=50 * 1024 * 1024, backupCount=2,
            encoding="utf-8",
        )
        handler.setLevel(level)
        handler.setFormatter(_JsonFormatter())
        handler.addFilter(flt)
        root_logger.addHandler(handler)
        _log_file_handlers.append(handler)
        return handler

    _make("backend.log", logging.INFO, _backend_all_filter)
    _make("frontend.log", logging.INFO, _frontend_all_filter)
    _make("errors.log", logging.ERROR, _errors_only_filter)
    return log_dir


def _write_port_file(root: Path) -> Path:
    port_file = lab_paths.port_file(root)
    try:
        port_file.parent.mkdir(parents=True, exist_ok=True)
        port_file.write_text(f"{config.port()}\n")
    except OSError:
        # Best effort; startup/switching should not fail because the port
        # discovery file could not be written.
        pass
    return port_file


def _remove_port_file(app: FastAPI) -> None:
    port_file = getattr(app.state, "workspace_port_file", None)
    if port_file is None:
        return
    try:
        Path(port_file).unlink(missing_ok=True)
    except OSError:
        pass
    app.state.workspace_port_file = None


def _stop_workspace_runtime(app: FastAPI) -> None:
    watcher = getattr(app.state, "index_watcher", None)
    if watcher is not None:
        watcher.stop()
        app.state.index_watcher = None
    _remove_port_file(app)
    _detach_file_logging()


def _start_workspace_runtime(app: FastAPI, root: Path, loop) -> None:
    root = root.expanduser().resolve()
    _attach_file_logging(root)
    port_file = _write_port_file(root)

    cache = IndexCache(root)
    cache.rebuild()

    def on_rebuild(_data) -> None:
        event = IndexUpdatedEvent(
            ts=datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        )
        asyncio.run_coroutine_threadsafe(app.state.ws_broadcaster.publish(event), loop)

    watcher = IndexWatcher(root, cache, debounce_ms=config.DEBOUNCE_MS, on_rebuild=on_rebuild)
    watcher.start()

    app.state.index_cache = cache
    app.state.index_watcher = watcher
    app.state.workspace_root = root
    app.state.workspace_port_file = port_file


# ── Split-file filters ──────────────────────────────────────────────────────
# Backend vs. frontend is decided by the ``source`` extra (default "server").
# Errors vs. non-errors is decided by levelno.

def _is_backend(r: logging.LogRecord) -> bool:
    return getattr(r, "source", "server") != "client"


def _is_frontend(r: logging.LogRecord) -> bool:
    return getattr(r, "source", "server") == "client"


def _backend_all_filter(r: logging.LogRecord) -> bool:
    return _is_backend(r)


def _frontend_all_filter(r: logging.LogRecord) -> bool:
    return _is_frontend(r)


def _errors_only_filter(r: logging.LogRecord) -> bool:
    return r.levelno >= logging.ERROR


# ── HTTP request middleware ─────────────────────────────────────────────────
# Logs every response. 2xx/3xx → INFO, 4xx → WARNING, 5xx → ERROR. Unhandled
# exceptions are logged with exc_info before FastAPI turns them into 500s.

_REQUEST_LOG = logging.getLogger("core.http")


async def _request_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    start_path = request.url.path
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _REQUEST_LOG.exception(
            "HTTP %s %s -> 500 %.2fms",
            request.method,
            start_path,
            duration_ms,
            extra={
                "method": request.method,
                "path_info": start_path,
                "route": getattr(request.scope.get("route"), "path", None),
                "status_code": 500,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
            },
        )
        raise
    code = response.status_code
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    route = getattr(request.scope.get("route"), "path", None)
    final_path = request.scope.get("path") or start_path
    if request.method == "GET" and final_path == "/" and code < 400:
        return response
    extra = {
        "method": request.method,
        "path_info": final_path,
        "route": route,
        "status_code": code,
        "duration_ms": duration_ms,
        "client": request.client.host if request.client else None,
    }
    level_override = getattr(request.state, "log_level_override", None)
    if isinstance(level_override, int):
        _REQUEST_LOG.log(
            level_override,
            "HTTP %s %s -> %d %.2fms",
            request.method,
            final_path,
            code,
            duration_ms,
            extra=extra,
        )
    elif code >= 500:
        _REQUEST_LOG.error(
            "HTTP %s %s -> %d %.2fms",
            request.method,
            final_path,
            code,
            duration_ms,
            extra=extra,
        )
    elif code >= 400:
        _REQUEST_LOG.warning(
            "HTTP %s %s -> %d %.2fms",
            request.method,
            final_path,
            code,
            duration_ms,
            extra=extra,
        )
    else:
        _REQUEST_LOG.info(
            "HTTP %s %s -> %d %.2fms",
            request.method,
            final_path,
            code,
            duration_ms,
            extra=extra,
        )
    return response


# Captures the `/api/proxy/<project>/<name>` prefix from a Referer URL.
# Used by the rewrite middleware below to forward absolute-path
# sub-resource requests (e.g. `/api/data`, `/socket.io/...`) from a
# proxied iframe back through the matching proxy mount.
import re as _re  # local alias to avoid colliding with `re` imports elsewhere

_PROXY_REFERER_RE = _re.compile(
    r"^https?://[^/]+(/api/proxy/[^/]+/[^/]+)(?:/|$)"
)
_PROXY_REFERER_SKIP_PREFIXES = (
    # Shared Lab endpoints that embedded/proxied apps intentionally call.
    # Rewriting them into the proxied dev server breaks state sync and
    # client-side logging.
    "/api/appstate/",
    "/api/log/",
)


async def _proxy_referer_rewrite(request: Request, call_next):
    """Re-route absolute-path requests from a proxy iframe.

    When the page inside an `/api/proxy/<project>/<name>/` iframe makes
    `fetch('/api/data')`, the browser sends it to the lab origin's
    root, which 404s. By inspecting `Referer` we can tell the request
    actually came from inside that iframe and silently rewrite the
    target path to land under the same proxy mount.

    Skipped when the path is already under `/api/proxy/` or
    `/ws/proxy/` (already targeting the proxy explicitly), so the
    middleware never recurses.

    Lab UI requests (Referer == lab root, e.g. `http://localhost:3333/`)
    don't match the proxy-mount regex and pass through untouched.
    """
    path = request.url.path
    if (
        path.startswith("/api/proxy/")
        or path.startswith("/ws/proxy/")
        or any(path.startswith(prefix) for prefix in _PROXY_REFERER_SKIP_PREFIXES)
    ):
        return await call_next(request)
    referer = request.headers.get("referer") or ""
    m = _PROXY_REFERER_RE.match(referer)
    if not m:
        return await call_next(request)
    mount = m.group(1)  # e.g. "/api/proxy/asta-gofundme-revamp/8080"
    new_path = mount + path
    # Mutate the ASGI scope so downstream route matching sees the
    # rewritten path. `raw_path` is the bytes version used by Starlette
    # for routing; both must be updated.
    request.scope["path"] = new_path
    request.scope["raw_path"] = new_path.encode("latin-1")
    return await call_next(request)


_PKG_DIR = Path(__file__).parent
_STATIC_DIR = _PKG_DIR / "static"
_TEMPLATES_DIR = _PKG_DIR / "templates"
try:
    _INDEX_TEMPLATE_CHECK_INTERVAL_S = max(
        1.0, float(os.environ.get("LAB_INDEX_TEMPLATE_CHECK_INTERVAL_S", "30"))
    )
except ValueError:
    _INDEX_TEMPLATE_CHECK_INTERVAL_S = 30.0


class _ImmutableStaticFiles(StaticFiles):
    """StaticFiles with a far-future immutable Cache-Control header.

    Used for ``/static/vendor`` only: every file there lives in a
    version-stamped directory (``xterm@5.3.0/...``), so its content can
    never change under the same URL. The browser then skips even the
    304-revalidation round trip on reloads — the PWA cold-start fetches
    exactly one HTML document and reads everything else from disk cache.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    root = config.monorepo_root()
    broadcaster = WsBroadcaster()
    loop = asyncio.get_running_loop()
    app.state.ws_broadcaster = broadcaster
    app.state.workspace_switch_lock = threading.Lock()

    def switch_workspace(next_root: Path) -> None:
        next_root = next_root.expanduser().resolve()
        with app.state.workspace_switch_lock:
            current = getattr(app.state, "index_cache", None)
            if current is not None and Path(current.root).resolve() == next_root:
                return
            _stop_workspace_runtime(app)
            _start_workspace_runtime(app, next_root, loop)

    app.state.switch_workspace = switch_workspace
    _start_workspace_runtime(app, root, loop)

    # Dev-server supervisor: re-resolves the active workspace root on every
    # tick (via app.state.index_cache.root), so it survives `switch_workspace`
    # without needing to be restarted. Gated by LAB_SERVER_SUPERVISOR.
    servers_route.start_supervisor(app)

    # Print useful URLs on boot (absorbed from gdiff's on_startup).
    try:
        from core.diff_parser import get_registered_repos

        projects = get_registered_repos()
        port = config.port()
        print("\n  core server URLs:")
        print(f"  http://localhost:{port}/")
        for proj in projects:
            print(f"  http://localhost:{port}/?project={quote(proj['path'], safe='')}")
        print()
    except Exception:
        pass

    try:
        yield
    finally:
        servers_route.stop_supervisor()
        _stop_workspace_runtime(app)


def create_app() -> FastAPI:
    app = FastAPI(
        title="lab-core",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    # Allow local dev frontends (Vite, Live Server, etc.) in addition to same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://localhost(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Log every HTTP response into the backend regular log, with ERROR+ split
    # into the errors-only files.
    app.middleware("http")(_request_log_middleware)

    # When a proxied app fetches an absolute path like `/api/data` or
    # `/socket.io/...` from inside the iframe, it lands on the lab
    # origin's root — not under the proxy mount — and gets a 404. This
    # middleware inspects the `Referer` header and, if it points at a
    # /api/proxy/<project>/<name>/ mount, rewrites the incoming path
    # to be under that mount. Lab UI's own requests (Referer == lab
    # root page, or no Referer) are unaffected.
    app.middleware("http")(_proxy_referer_rewrite)

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(appstate_route.router)
    app.include_router(index_route.router)
    app.include_router(project_route.router)
    app.include_router(task_route.router)
    app.include_router(markdown_route.router)
    app.include_router(notebook_route.router)
    app.include_router(nb_exec_route.router)
    app.include_router(ws_route.router)
    app.include_router(mutation_route.router)
    app.include_router(search_route.router)
    app.include_router(diff_route.router)
    app.include_router(term_route.router)
    app.include_router(servers_route.router)
    app.include_router(cerebro_route.router)
    app.include_router(ui_route.router)
    app.include_router(workspace_route.router)
    app.include_router(log_route.router)
    app.include_router(git_route.router)
    app.include_router(proxy_route.router)
    app.include_router(code_search_route.router)
    app.include_router(settings_route.router)

    # Mounted before /static so the more specific path wins: vendored,
    # version-stamped libraries get immutable caching; everything else under
    # /static keeps the default ETag/304 behavior.
    app.mount(
        "/static/vendor",
        _ImmutableStaticFiles(directory=_STATIC_DIR / "vendor"),
        name="vendor",
    )
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # The index template is large enough that re-rendering it through Jinja on
    # every load costs more than serving the bytes. The first visible shell does
    # vary by URL, so cache a small set of rendered variants keyed by template
    # mtime and initial view state.
    _index_cache: dict = {"mtime": None, "bytes_by_key": {}, "check_after": 0.0}

    def _index_initial_state(request: Request) -> dict:
        params = request.query_params
        view = params.get("view") or ""
        project = params.get("project") or ""
        repo = params.get("repo") or ""

        if view == "productivity":
            return {
                "INITIAL_VIEW": "productivity",
                "INITIAL_BODY_CLASS": "self-active",
                "INITIAL_PROJECT_NAME": "",
                "INITIAL_IS_REPO": False,
            }
        if view == "workspace":
            return {
                "INITIAL_VIEW": "workspace",
                "INITIAL_BODY_CLASS": "workspace-active",
                "INITIAL_PROJECT_NAME": "",
                "INITIAL_IS_REPO": False,
            }
        if view == "cerebro":
            return {
                "INITIAL_VIEW": "cerebro",
                "INITIAL_BODY_CLASS": "cerebro-active",
                "INITIAL_PROJECT_NAME": "",
                "INITIAL_IS_REPO": False,
            }
        if view == "code-search":
            return {
                "INITIAL_VIEW": "code-search",
                "INITIAL_BODY_CLASS": "code-search-active",
                "INITIAL_PROJECT_NAME": "",
                "INITIAL_IS_REPO": False,
            }
        if view == "logs":
            return {
                "INITIAL_VIEW": "logs",
                "INITIAL_BODY_CLASS": "logs-active",
                "INITIAL_PROJECT_NAME": "",
                "INITIAL_IS_REPO": False,
            }
        if project or repo:
            target = (repo or project).rstrip("/")
            name = Path(target).name or ("Repository" if repo else "Project")
            return {
                "INITIAL_VIEW": "repo" if repo else "project",
                "INITIAL_BODY_CLASS": "project-active",
                "INITIAL_PROJECT_NAME": name,
                "INITIAL_IS_REPO": bool(repo),
            }
        return {
            "INITIAL_VIEW": "home",
            "INITIAL_BODY_CLASS": "home-active",
            "INITIAL_PROJECT_NAME": "",
            "INITIAL_IS_REPO": False,
        }

    def _compact_index_html(html: str) -> str:
        html = _re.sub(r"<!--.*?-->", "", html, flags=_re.S)
        return _re.sub(r">\s+<", "><", html)

    # Assets the shell loads without a fingerprinted filename. Their mtimes
    # feed the ?v= cache-buster below so browsers (notably the installed PWA)
    # pick up UI changes without a hard reload.
    _index_asset_files = (
        _TEMPLATES_DIR / "index.html",
        _STATIC_DIR / "js" / "lab-app.js",
        _STATIC_DIR / "css" / "lab-shell.css",
        _STATIC_DIR / "js" / "lib" / "error-report.js",
    )

    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        root = Path(request.app.state.index_cache.root).expanduser().resolve()
        workspace_root = str(root)
        mtime = _index_cache["mtime"]
        now = time.monotonic()
        if now >= _index_cache["check_after"]:
            _index_cache["check_after"] = now + _INDEX_TEMPLATE_CHECK_INTERVAL_S
            try:
                mtime = tuple(f.stat().st_mtime_ns for f in _index_asset_files)
            except OSError:
                mtime = None
        state = _index_initial_state(request)
        key = (
            workspace_root,
            state["INITIAL_VIEW"],
            state["INITIAL_BODY_CLASS"],
            state["INITIAL_PROJECT_NAME"],
            state["INITIAL_IS_REPO"],
        )
        if mtime is None or _index_cache["mtime"] != mtime:
            _index_cache["bytes_by_key"] = {}
            _index_cache["mtime"] = mtime
        bytes_by_key = _index_cache["bytes_by_key"]
        if key not in bytes_by_key:
            asset_v = format(max(mtime) // 1_000_000, "x") if mtime else "0"
            html = templates.get_template("index.html").render(
                MONOREPO_ROOT=str(lab_paths.find_framework_root()),
                WORKSPACE_ROOT=workspace_root,
                ASSET_V=asset_v,
                **state,
            )
            bytes_by_key[key] = _compact_index_html(html).encode("utf-8")
        # no-cache = always revalidate the tiny HTML shell; the big assets it
        # references carry ?v= fingerprints and stay cacheable. Without this,
        # browsers may reuse a cached shell pointing at stale asset URLs.
        return Response(
            bytes_by_key[key],
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/p/{project_id}")
    async def spa_project(request: Request, project_id: str):
        """D3 URL: /p/<id> redirects to /?project=<abs path>.

        The source of truth remains ``?project=<abs path>`` (gdiff's existing
        muscle memory); /p/<id> is sugar for project-id navigation.
        """
        root: Path = request.app.state.index_cache.root
        project_dir = (root / "projects" / project_id).resolve()
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
        return RedirectResponse(url=f"/?project={quote(str(project_dir), safe='')}")

    @app.get("/view", response_class=HTMLResponse)
    async def view_markdown(request: Request, path: str):
        """Render a markdown file under `content/` as a standalone HTML page.

        Used by the Home view's Search tab so clicking a doc result shows the
        rendered page instead of the raw `/api/markdown` JSON. Reuses the same
        renderer + path-safety checks as `/api/markdown`.
        """
        from core.routes.markdown import _RENDERER, _FRONTMATTER_RE, _safe_resolve
        import yaml

        root: Path = request.app.state.index_cache.root
        target = _safe_resolve(root, path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="not found")

        text = target.read_text(encoding="utf-8")
        frontmatter: dict = {}
        body = text
        m = _FRONTMATTER_RE.match(text)
        if m:
            try:
                frontmatter = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                frontmatter = {}
            body = text[m.end():]

        _RENDERER.reset()
        html = _RENDERER.convert(body)

        title = frontmatter.get("title") or Path(path).stem
        fm_html = ""
        if frontmatter:
            bits = []
            for k in ("date", "type", "scope", "projects", "tags"):
                if k in frontmatter:
                    v = frontmatter[k]
                    if isinstance(v, list):
                        v = ", ".join(str(x) for x in v)
                    bits.append(f"<span class='fm-chip'><b>{k}:</b> {v}</span>")
            if bits:
                fm_html = "<div class='fm-row'>" + " ".join(bits) + "</div>"

        page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="stylesheet" href="/static/vendor/highlightjs@11.9.0/github-dark.min.css">
<style>
  body {{ background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 820px; margin: 0 auto; padding: 40px 24px 80px; line-height: 1.7; }}
  a {{ color: #58a6ff; }}
  h1, h2, h3 {{ color: #fff; border-bottom: 1px solid #30363d; padding-bottom: 6px; margin-top: 32px; }}
  code {{ background: #161b22; padding: 2px 6px; border-radius: 3px; font-size: 90%; }}
  pre {{ background: #161b22; padding: 14px; border-radius: 6px; overflow-x: auto; }}
  pre code {{ background: transparent; padding: 0; }}
  blockquote {{ border-left: 3px solid #30363d; padding-left: 14px; color: #8b949e; margin: 10px 0; }}
  table {{ border-collapse: collapse; margin: 12px 0; }}
  td, th {{ border: 1px solid #30363d; padding: 6px 10px; }}
  th {{ background: #161b22; }}
  .topbar {{ margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #30363d; display: flex; gap: 12px; align-items: baseline; }}
  .topbar a {{ color: #8b949e; text-decoration: none; font-size: 13px; }}
  .topbar a:hover {{ color: #e6edf3; }}
  .topbar .path {{ font-family: ui-monospace, monospace; font-size: 12px; color: #8b949e; }}
  .fm-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 24px; }}
  .fm-chip {{ background: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 3px 10px; font-size: 12px; color: #8b949e; }}
  .fm-chip b {{ color: #e6edf3; font-weight: 500; }}
</style>
</head><body>
<div id="__js_errors__" data-errors="" style="display:none;position:fixed;top:0;right:0;z-index:9999;background:#f85149;color:#fff;font:11px/1.4 ui-monospace,monospace;padding:6px 10px;max-width:520px;white-space:pre-wrap;border-bottom-left-radius:6px"></div>
<script src="/static/js/lib/error-report.js"></script>
<script>
(function() {{
  var box = document.getElementById('__js_errors__');
  function add(m) {{ var p = box.getAttribute('data-errors') || ''; box.setAttribute('data-errors', p + m + '\\n'); box.textContent = (p + m + '\\n').trim(); box.style.display = 'block'; }}
  window.addEventListener('error', function(e) {{ add((e.message || 'Error') + ' @ ' + (e.filename || '') + ':' + (e.lineno || '?')); }});
  window.addEventListener('unhandledrejection', function(e) {{ add('Unhandled: ' + (e.reason && e.reason.message ? e.reason.message : e.reason)); }});
}})();
</script>
<div class="topbar">
  <a href="/">&larr; Home</a>
  <span class="path">{path}</span>
</div>
<h1>{title}</h1>
{fm_html}
{html}
<script src="/static/vendor/highlightjs@11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
</body></html>"""
        return HTMLResponse(page)

    return app


app = create_app()


def run() -> None:
    import os

    import uvicorn

    reload = os.environ.get("LAB_RELOAD") == "1"
    kwargs: dict = {
        "host": config.host(),
        "port": config.port(),
        "reload": reload,
        "access_log": False,
        "timeout_graceful_shutdown": 5,
        # Terminal traffic is hundreds of tiny frames per second; permessage-
        # deflate buys nothing on localhost and adds per-frame compression
        # latency + CPU on both ends. Off for low-latency keystroke echo.
        "ws_per_message_deflate": False,
    }
    if reload:
        kwargs["reload_dirs"] = [str(Path(__file__).resolve().parent)]
    uvicorn.run("core.main:app", **kwargs)
