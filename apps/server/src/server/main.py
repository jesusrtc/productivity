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
from server.routes import diff as diff_route
from server.routes import index as index_route
from server.routes import log as log_route
from server.routes import markdown as markdown_route
from server.routes import mutation as mutation_route
from server.routes import notebook as notebook_route
from server.routes import project as project_route
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

# Keep a module-level reference so lifespan can remove it on shutdown.
_file_handler: logging.handlers.RotatingFileHandler | None = None


_PKG_DIR = Path(__file__).parent
_STATIC_DIR = _PKG_DIR / "static"
_TEMPLATES_DIR = _PKG_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _file_handler
    root = config.monorepo_root()

    # ── File logging setup ──────────────────────────────────────────────────
    # Attach a RotatingFileHandler to the root logger so WARNING+ from every
    # source (uvicorn, FastAPI, our code, third-party libs) lands in
    # logs/server.log.  We add the handler HERE (after uvicorn has configured
    # its own handlers) so we don't conflict with basicConfig / dictConfig.
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
        # Remove and close the file handler to flush any buffered records.
        if _file_handler is not None:
            logging.getLogger().removeHandler(_file_handler)
            _file_handler.close()


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

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(index_route.router)
    app.include_router(project_route.router)
    app.include_router(task_route.router)
    app.include_router(markdown_route.router)
    app.include_router(notebook_route.router)
    app.include_router(ws_route.router)
    app.include_router(mutation_route.router)
    app.include_router(search_route.router)
    app.include_router(diff_route.router)
    app.include_router(term_route.router)
    app.include_router(cerebro_route.router)
    app.include_router(ui_route.router)
    app.include_router(log_route.router)

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
        project_dir = (root / "knowledge" / "projects" / project_id).resolve()
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"project {project_id!r} not found")
        return RedirectResponse(url=f"/?project={quote(str(project_dir), safe='')}")

    @app.get("/view", response_class=HTMLResponse)
    async def view_markdown(request: Request, path: str):
        """Render a markdown file under `knowledge/` as a standalone HTML page.

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
