from __future__ import annotations

import json
import logging
import logging.handlers
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server import config
from server.routes import cerebro as cerebro_route
from server.routes import code_search as code_search_route
from server.routes import diff as diff_route
from server.routes import git as git_route
from server.routes import index as index_route
from server.routes import log as log_route
from server.routes import markdown as markdown_route
from server.routes import mutation as mutation_route
from server.routes import nb_exec as nb_exec_route
from server.routes import notebook as notebook_route
from server.routes import project as project_route
from server.routes import proxy as proxy_route
from server.routes import search as search_route
from server.routes import task as task_route
from server.routes import term as term_route
from server.routes import ui as ui_route
from server.routes import ws as ws_route
from server.state import IndexCache, IndexUpdatedEvent, WsBroadcaster
from server.watcher import IndexWatcher


# ─── Structured file logging ─────────────────────────────────────────────────
# Single JSON-lines formatter used by the rotating file handler attached to
# the root logger during lifespan startup.  Console output is unchanged.

class _JsonFormatter(logging.Formatter):
    """Newline-delimited JSON log entries for logs/server.log.

    Fields: ts, level, logger, source, msg, path, exc (if any), session_id (if any).
    Server entries derive ``path`` from the LogRecord's filename:lineno.
    Client entries (from routes/log.py) carry ``source="client"`` and
    ``path_info`` via the ``extra`` dict; the formatter routes them correctly.
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        )
        source = getattr(record, "source", "server")
        if source == "client":
            path = getattr(record, "path_info", "")
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
        return json.dumps(entry, ensure_ascii=False)

# Keep module-level references so lifespan can remove them on shutdown.
_file_handler: logging.handlers.RotatingFileHandler | None = None
_split_handlers: list[logging.Handler] = []


# ── Split-file filters ──────────────────────────────────────────────────────
# Backend vs. frontend is decided by the ``source`` extra (default "server").
# Errors vs. non-errors is decided by levelno.

def _is_backend(r: logging.LogRecord) -> bool:
    return getattr(r, "source", "server") != "client"


def _is_frontend(r: logging.LogRecord) -> bool:
    return getattr(r, "source", "server") == "client"


def _backend_errors_filter(r: logging.LogRecord) -> bool:
    return _is_backend(r) and r.levelno >= logging.WARNING


def _backend_info_filter(r: logging.LogRecord) -> bool:
    return _is_backend(r) and r.levelno < logging.WARNING


def _frontend_errors_filter(r: logging.LogRecord) -> bool:
    return _is_frontend(r) and r.levelno >= logging.ERROR


def _frontend_info_filter(r: logging.LogRecord) -> bool:
    return _is_frontend(r) and r.levelno < logging.ERROR


# ── HTTP request middleware ─────────────────────────────────────────────────
# Logs every response. 4xx → WARNING, 5xx → ERROR. These flow through the root
# logger, which means they hit logs/backend-errors.log via the WARNING-level
# split handler. Without this middleware, "404"-class failures only show up in
# uvicorn's INFO access log and aren't captured anywhere persistent.

_REQUEST_LOG = logging.getLogger("server.http")


async def _request_log_middleware(request: Request, call_next):
    response = await call_next(request)
    code = response.status_code
    if code >= 500:
        _REQUEST_LOG.error("%s %s -> %d", request.method, request.url.path, code)
    elif code >= 400:
        _REQUEST_LOG.warning("%s %s -> %d", request.method, request.url.path, code)
    return response


# Captures the `/api/proxy/<project>/<name>` prefix from a Referer URL.
# Used by the rewrite middleware below to forward absolute-path
# sub-resource requests (e.g. `/api/data`, `/socket.io/...`) from a
# proxied iframe back through the matching proxy mount.
import re as _re  # local alias to avoid colliding with `re` imports elsewhere

_PROXY_REFERER_RE = _re.compile(
    r"^https?://[^/]+(/api/proxy/[^/]+/[^/]+)(?:/|$)"
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
    if path.startswith("/api/proxy/") or path.startswith("/ws/proxy/"):
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _file_handler
    root = config.monorepo_root()

    # ── File logging setup ──────────────────────────────────────────────────
    # Five files land in ``logs/`` so future Claude turns can tail the smallest
    # relevant one without scanning a 200KB combined log:
    #
    #   server.log              — legacy combined (WARNING+), 10MB×5 rotation.
    #   backend-errors.log      — backend WARNING+ only (incl. 4xx/5xx via
    #                             _request_log_middleware). Long retention.
    #   backend-info.log        — backend INFO/DEBUG. Daily rotation, 3 days.
    #   frontend-errors.log     — client-side ERROR events (from /api/log/client).
    #   frontend-info.log       — client-side WARNING events. Daily, 3 days.
    #
    # The split is done with filters on the JSON formatter; ``source`` is
    # "server" for backend records and "client" for events POSTed by the
    # browser via routes/log.py.
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)

    _file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    _file_handler.setLevel(logging.WARNING)
    _file_handler.setFormatter(_JsonFormatter())
    logging.getLogger().addHandler(_file_handler)

    # Split files. The root logger's effective level needs to allow INFO
    # through so the info-level split handlers see anything at all — but we
    # leave each handler's own level/filter to do the gating, so the console
    # output uvicorn already configured is unaffected.
    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)

    _split_handlers.clear()

    def _make(handler: logging.Handler, level: int, flt) -> logging.Handler:
        handler.setLevel(level)
        handler.setFormatter(_JsonFormatter())
        handler.addFilter(flt)
        root_logger.addHandler(handler)
        _split_handlers.append(handler)
        return handler

    _make(
        logging.handlers.RotatingFileHandler(
            log_dir / "backend-errors.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        ),
        logging.WARNING,
        _backend_errors_filter,
    )
    _make(
        logging.handlers.TimedRotatingFileHandler(
            log_dir / "backend-info.log",
            when="midnight",
            interval=1,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.INFO,
        _backend_info_filter,
    )
    _make(
        logging.handlers.RotatingFileHandler(
            log_dir / "frontend-errors.log",
            maxBytes=50 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        ),
        logging.ERROR,
        _frontend_errors_filter,
    )
    _make(
        logging.handlers.TimedRotatingFileHandler(
            log_dir / "frontend-info.log",
            when="midnight",
            interval=1,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.WARNING,
        _frontend_info_filter,
    )

    # Drop the running port to disk so other tools (lab CLI, scripts, Claude
    # curl examples) can discover it without hardcoding 3333. Removed in the
    # finally block on shutdown.
    port_file = root / ".lab-server.port"
    try:
        port_file.write_text(f"{config.port()}\n")
    except OSError:
        # Best effort — don't block startup if the FS is read-only or full.
        pass

    cache = IndexCache(root)
    broadcaster = WsBroadcaster()

    cache.rebuild()

    import asyncio
    loop = asyncio.get_running_loop()

    def on_rebuild(_data) -> None:
        event = IndexUpdatedEvent(ts=datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds"))
        asyncio.run_coroutine_threadsafe(broadcaster.publish(event), loop)

    watcher = IndexWatcher(root, cache, debounce_ms=config.DEBOUNCE_MS, on_rebuild=on_rebuild)
    watcher.start()

    app.state.index_cache = cache
    app.state.ws_broadcaster = broadcaster
    app.state.index_watcher = watcher

    # Print useful URLs on boot (absorbed from gdiff's on_startup).
    try:
        from server.diff_parser import get_registered_repos

        projects = get_registered_repos()
        port = config.port()
        print("\n  lab-server URLs:")
        print(f"  http://localhost:{port}/")
        for proj in projects:
            print(f"  http://localhost:{port}/?project={quote(proj['path'], safe='')}")
        print()
    except Exception:
        pass

    try:
        yield
    finally:
        watcher.stop()
        try:
            port_file.unlink(missing_ok=True)
        except OSError:
            pass
        # Remove and close the file handlers to flush any buffered records.
        if _file_handler is not None:
            logging.getLogger().removeHandler(_file_handler)
            _file_handler.close()
        for h in _split_handlers:
            logging.getLogger().removeHandler(h)
            h.close()
        _split_handlers.clear()


def create_app() -> FastAPI:
    app = FastAPI(title="lab-server", version="0.1.0", lifespan=lifespan)

    # Allow local dev frontends (Vite, Live Server, etc.) in addition to same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://localhost(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Log 4xx/5xx responses into the backend-errors split file.
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
    app.include_router(cerebro_route.router)
    app.include_router(ui_route.router)
    app.include_router(log_route.router)
    app.include_router(git_route.router)
    app.include_router(proxy_route.router)
    app.include_router(code_search_route.router)

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index_page(request: Request):
        root: Path = request.app.state.index_cache.root
        return templates.TemplateResponse(
            request, "index.html", {"MONOREPO_ROOT": str(root)}
        )

    @app.get("/p/{project_id}")
    async def spa_project(request: Request, project_id: str):
        """D3 URL: /p/<id> redirects to /?project=<abs path>.

        The source of truth remains ``?project=<abs path>`` (gdiff's existing
        muscle memory); /p/<id> is sugar for project-id navigation.
        """
        root: Path = request.app.state.index_cache.root
        project_dir = (root / "content" / "projects" / project_id).resolve()
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
        from server.routes.markdown import _RENDERER, _FRONTMATTER_RE, _safe_resolve
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
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
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
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
</body></html>"""
        return HTMLResponse(page)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=config.host(),
        port=config.port(),
        reload=False,
        timeout_graceful_shutdown=5,
    )
