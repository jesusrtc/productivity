from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from html import escape
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from lab import paths


SESSION_COOKIE = "lab_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
HOME_WORKSPACE = "__home__"
STORE_VERSION = 2
BUILTIN_ADMIN_USERNAME = "admin"

_LOCK = threading.RLock()
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{1,40}$")
_SEED_USERS = (
    (BUILTIN_ADMIN_USERNAME, "Admin", "admin", "admin"),
)


def auth_file() -> Path:
    """Global auth state; permissions span the global workspace registry."""
    return paths.global_config_dir() / "auth.json"


def password_sha256(password: str) -> str:
    """Intentionally basic local-only password hashing requested by the user."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError("username must use only letters, numbers, dot, dash, or underscore")
    return username


def _seed_row(username: str, name: str, role: str, password: str) -> dict[str, Any]:
    return {
        "username": username,
        "name": name,
        "role": role,
        "password_sha256": password_sha256(password),
        "workspaces": [],
        "disabled": False,
    }


def _default_store() -> dict[str, Any]:
    return {
        "version": STORE_VERSION,
        "secret": secrets.token_hex(32),
        "users": [_seed_row(*seed) for seed in _SEED_USERS],
    }


def _atomic_write(data: dict[str, Any]) -> None:
    target = auth_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _normalize_store(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    if not isinstance(data.get("secret"), str) or not data["secret"]:
        data["secret"] = secrets.token_hex(32)
        changed = True
    # Version 2 intentionally replaces the old jesus/cesar/miriam bootstrap
    # with one fixed local administrator. Additional accounts are created by
    # that administrator from the Admin tab after migration.
    if data.get("version") != STORE_VERSION:
        data["users"] = [_seed_row(*seed) for seed in _SEED_USERS]
        data["version"] = STORE_VERSION
        changed = True

    raw_users = data.get("users")
    if not isinstance(raw_users, list):
        raw_users = []
        data["users"] = raw_users
        changed = True

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_users:
        if not isinstance(raw, dict):
            changed = True
            continue
        try:
            username = normalize_username(str(raw.get("username") or ""))
        except ValueError:
            changed = True
            continue
        if username in seen:
            changed = True
            continue
        seen.add(username)
        role = "admin" if raw.get("role") == "admin" else "user"
        workspaces = raw.get("workspaces")
        if not isinstance(workspaces, list):
            workspaces = []
            changed = True
        row = {
            "username": username,
            "name": str(raw.get("name") or username.title()).strip() or username.title(),
            "role": role,
            "password_sha256": str(raw.get("password_sha256") or ""),
            "workspaces": sorted({str(w) for w in workspaces if isinstance(w, str) and w}),
            "disabled": bool(raw.get("disabled", False)),
        }
        if row != raw:
            changed = True
        normalized.append(row)

    for username, name, role, password in _SEED_USERS:
        if username not in seen:
            normalized.append(_seed_row(username, name, role, password))
            seen.add(username)
            changed = True
    builtin = _seed_row(*_SEED_USERS[0])
    for index, row in enumerate(normalized):
        if row.get("username") == BUILTIN_ADMIN_USERNAME and row != builtin:
            normalized[index] = builtin
            changed = True
    if normalized != raw_users:
        data["users"] = normalized
        changed = True
    data["version"] = STORE_VERSION
    return data, changed


def load_store() -> dict[str, Any]:
    with _LOCK:
        target = auth_file()
        if not target.is_file():
            data = _default_store()
            _atomic_write(data)
            return data
        try:
            target.chmod(0o600)
        except OSError:
            pass
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            loaded = _default_store()
            _atomic_write(loaded)
            return loaded
        if not isinstance(loaded, dict):
            loaded = _default_store()
            _atomic_write(loaded)
            return loaded
        data, changed = _normalize_store(loaded)
        if changed:
            _atomic_write(data)
        return data


def save_store(data: dict[str, Any]) -> None:
    with _LOCK:
        normalized, _ = _normalize_store(data)
        _atomic_write(normalized)


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": row["username"],
        "name": row.get("name") or row["username"].title(),
        "role": row.get("role") or "user",
        "workspaces": list(row.get("workspaces") or []),
        "disabled": bool(row.get("disabled", False)),
        "built_in": row.get("username") == BUILTIN_ADMIN_USERNAME,
    }


def get_user(username: str) -> dict[str, Any] | None:
    try:
        wanted = normalize_username(username)
    except ValueError:
        return None
    for row in load_store().get("users") or []:
        if row.get("username") == wanted:
            return dict(row)
    return None


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    row = get_user(username)
    if row is None or row.get("disabled"):
        return None
    candidate = password_sha256(password)
    if not hmac.compare_digest(candidate, str(row.get("password_sha256") or "")):
        return None
    return row


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def issue_session(row: dict[str, Any], *, now: int | None = None) -> str:
    store = load_store()
    issued = int(time.time() if now is None else now)
    payload = {
        "u": row["username"],
        "exp": issued + SESSION_MAX_AGE,
        # A password change invalidates every cookie issued with the old hash.
        "p": str(row.get("password_sha256") or "")[:16],
    }
    encoded = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        str(store["secret"]).encode("utf-8"), encoded.encode("ascii"), hashlib.sha256,
    ).digest()
    return f"{encoded}.{_b64_encode(signature)}"


def verify_session(token: str, *, now: int | None = None) -> dict[str, Any] | None:
    try:
        encoded, raw_signature = token.split(".", 1)
        store = load_store()
        expected = hmac.new(
            str(store["secret"]).encode("utf-8"), encoded.encode("ascii"), hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64_decode(raw_signature)):
            return None
        payload = json.loads(_b64_decode(encoded).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time() if now is None else now):
            return None
        row = next(
            (dict(user) for user in store.get("users") or [] if user.get("username") == payload.get("u")),
            None,
        )
        if row is None or row.get("disabled"):
            return None
        if payload.get("p") != str(row.get("password_sha256") or "")[:16]:
            return None
        return row
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _cookie_value(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def user_from_connection(connection: Request | WebSocket) -> dict[str, Any] | None:
    cached = getattr(connection.state, "auth_user", None)
    if cached is not None:
        return cached
    token = _cookie_value(connection.headers.get("cookie"))
    row = verify_session(token) if token else None
    if row is not None:
        connection.state.auth_user = row
    return row


def require_user(connection: Request | WebSocket) -> dict[str, Any]:
    row = user_from_connection(connection)
    if row is None:
        raise HTTPException(status_code=401, detail="login required")
    return row


def require_admin(connection: Request | WebSocket) -> dict[str, Any]:
    row = require_user(connection)
    if row.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return row


def is_admin(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("role") == "admin")


def allowed_workspace_ids(row: dict[str, Any] | None) -> set[str]:
    if is_admin(row):
        return {
            str(workspace.get("id"))
            for workspace in paths.read_workspace_registry().get("workspaces") or []
            if workspace.get("id")
        }
    return {str(value) for value in (row or {}).get("workspaces") or [] if value}


def can_access_workspace(row: dict[str, Any] | None, workspace_id: str) -> bool:
    return is_admin(row) or workspace_id in allowed_workspace_ids(row)


def require_workspace(connection: Request | WebSocket, workspace_id: str) -> dict[str, Any]:
    row = require_user(connection)
    if not can_access_workspace(row, workspace_id):
        # Do not disclose whether an unassigned workspace exists.
        raise HTTPException(status_code=404, detail="workspace not found")
    return row


def workspace_id_for_root(root: Path) -> str | None:
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        return None
    for row in paths.read_workspace_registry().get("workspaces") or []:
        try:
            if Path(str(row["path"])).expanduser().resolve() == resolved:
                return str(row["id"])
        except (KeyError, OSError):
            continue
    try:
        if resolved == paths.find_workspace_root().expanduser().resolve():
            return resolved.name
    except Exception:
        pass
    return None


def workspace_id_for_path(value: str | Path) -> str | None:
    try:
        target = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError):
        return None
    candidates: list[tuple[int, str, Path]] = []
    for row in paths.read_workspace_registry().get("workspaces") or []:
        try:
            root = Path(str(row["path"])).expanduser().resolve()
        except (KeyError, OSError):
            continue
        candidates.append((len(root.parts), str(row["id"]), root))
    for _depth, workspace_id, root in sorted(candidates, reverse=True):
        if target == root or root in target.parents:
            return workspace_id
    try:
        framework = paths.find_framework_root().expanduser().resolve()
        if target == framework or framework in target.parents:
            return HOME_WORKSPACE
    except Exception:
        pass
    return None


def first_allowed_workspace(row: dict[str, Any] | None) -> str | None:
    allowed = allowed_workspace_ids(row)
    for workspace in paths.read_workspace_registry().get("workspaces") or []:
        workspace_id = str(workspace.get("id") or "")
        if workspace_id and (is_admin(row) or workspace_id in allowed):
            return workspace_id
    return None


def workspace_root_for_id(workspace_id: str) -> Path | None:
    for row in paths.read_workspace_registry().get("workspaces") or []:
        if str(row.get("id")) != workspace_id:
            continue
        try:
            return Path(str(row["path"])).expanduser().resolve()
        except (KeyError, OSError):
            return None
    return None


def request_root(request: Request) -> Path:
    """Return the workspace root selected and authorized for this request."""
    scoped = getattr(getattr(request, "state", None), "auth_workspace_root", None)
    if scoped is not None:
        return Path(scoped).expanduser().resolve()
    return Path(request.app.state.index_cache.root).expanduser().resolve()


def request_index(request: Request) -> dict[str, Any]:
    """Read the request workspace index without switching global state."""
    root = request_root(request)
    cache = request.app.state.index_cache
    if Path(cache.root).expanduser().resolve() == root:
        return cache.get()
    from lab import index as index_mod

    return index_mod.build_index(root)


_ADMIN_PREFIXES = (
    "/api/admin/",
    "/api/cerebro/",
    "/api/code-search/",
    "/api/git/",
    "/api/log/files",
    "/api/log/error-state",
    "/api/log/tail",
)
_ADMIN_EXACT = {
    "/api/workspaces/use",
    "/api/agents/sync",
}
_GLOBAL_FILTERED_GETS = {
    "/api/workspaces",
    "/api/workspaces/projects",
    "/api/servers",
    "/api/term/projects-with-sessions",
}
_GLOBAL_USER_ENDPOINTS = {
    "/api/agents/available",
    "/api/auth/me",
    "/api/auth/logout",
}
_PSEUDO_ADMIN_RE = re.compile(r"__(?:self|cerebro|logs|cs_[^/]+)__")


def _is_admin_only_request(request: Request) -> bool:
    path = request.url.path
    if path in _ADMIN_EXACT or any(path.startswith(prefix) for prefix in _ADMIN_PREFIXES):
        return True
    if path == "/api/settings" and request.method != "GET":
        return True
    if path == "/api/workspaces" and request.method != "GET":
        return True
    if path == "/logs":
        return True
    return False


async def _json_request_body(request: Request) -> dict[str, Any]:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return {}
    content_type = request.headers.get("content-type") or ""
    if "application/json" not in content_type.lower():
        return {}
    try:
        value = await request.json()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _workspace_from_route_path(path: str) -> str | None:
    patterns = (
        r"^/api/workspace-proxy/([^/]+)(?:/|$)",
        r"^/api/servers/([^/]+)(?:/|$)",
        r"^/ws/workspace-proxy/([^/]+)(?:/|$)",
        r"^/api/workspaces/([^/]+)/(?:appearance)(?:/|$)",
    )
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


def _referer_scope(request: Request) -> tuple[str | None, str | None]:
    raw = request.headers.get("referer") or ""
    if not raw:
        return None, None
    try:
        query = parse_qs(urlparse(raw).query)
    except ValueError:
        return None, None
    workspace = (query.get("workspace") or [None])[0]
    for key in ("project", "repo"):
        value = (query.get(key) or [None])[0]
        if value and Path(value).is_absolute():
            return workspace, value
    return workspace, None


async def _request_scope(request: Request) -> tuple[str | None, str | None, str | None]:
    """Return (workspace id, absolute resource path, pseudo project id)."""
    body = await _json_request_body(request)
    workspace = request.query_params.get("workspace") or _workspace_from_route_path(request.url.path)
    if not workspace:
        raw_workspace = body.get("workspace")
        if isinstance(raw_workspace, str) and raw_workspace:
            workspace = raw_workspace

    resource: str | None = None
    for key in ("repo", "project", "path", "cwd"):
        value = request.query_params.get(key)
        if isinstance(value, str) and value and Path(value).is_absolute():
            resource = value
            break
        value = body.get(key)
        if isinstance(value, str) and value and Path(value).is_absolute():
            resource = value
            break
    referer_workspace, referer_resource = _referer_scope(request)
    workspace = workspace or referer_workspace
    if resource is None:
        resource = referer_resource

    pseudo: str | None = None
    candidates = [request.url.path, request.query_params.get("project_id") or ""]
    for key in ("project_id", "id"):
        value = body.get(key)
        if isinstance(value, str):
            candidates.append(value)
    for value in candidates:
        match = _PSEUDO_ADMIN_RE.search(value)
        if match:
            pseudo = match.group(0)
            break
    return workspace, resource, pseudo


def _no_workspace_page(row: dict[str, Any]) -> HTMLResponse:
    name = escape(str(row.get("name") or row.get("username") or "User"))
    body = f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>No workspace access</title>
    <style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:520px;padding:32px;border:1px solid #30363d;border-radius:10px;background:#161b22}}p{{color:#8b949e;line-height:1.6}}button{{border:1px solid #30363d;border-radius:6px;background:#21262d;color:#e6edf3;padding:8px 12px;cursor:pointer}}</style></head>
    <body><div id=\"__js_errors__\" data-errors=\"\" style=\"display:none\"></div><main><h1>No workspace assigned</h1><p>{name}, an admin needs to grant your account access to a workspace.</p><button id=\"signout\">Sign out</button></main><script>document.getElementById('signout').onclick=async()=>{{try{{await fetch('/api/auth/logout',{{method:'POST'}})}}catch{{}}location.replace('/login')}}</script></body></html>"""
    return HTMLResponse(body, status_code=403)


async def http_auth_middleware(request: Request, call_next) -> Response:
    path = request.url.path
    if (
        path == "/api/ping"
        or path == "/login"
        or path == "/api/auth/login"
        or path.startswith("/static/")
        or request.method == "OPTIONS"
    ):
        return await call_next(request)

    row = user_from_connection(request)
    if row is None:
        if path == "/" or not path.startswith("/api/"):
            target = request.url.path
            if request.url.query:
                target += "?" + request.url.query
            return RedirectResponse(url="/login?next=" + quote(target, safe=""), status_code=303)
        return JSONResponse({"detail": "login required"}, status_code=401)
    request.state.auth_user = row

    workspace, resource, pseudo = await _request_scope(request)
    owner = workspace_id_for_path(resource) if resource else None
    scoped_workspace = workspace or (owner if owner != HOME_WORKSPACE else None)
    scoped_root = workspace_root_for_id(scoped_workspace) if scoped_workspace else None
    if owner == HOME_WORKSPACE and is_admin(row):
        try:
            scoped_root = paths.find_framework_root().expanduser().resolve()
        except Exception:
            scoped_root = None
    if scoped_root is not None:
        request.state.auth_workspace_root = scoped_root

    if is_admin(row):
        return await call_next(request)

    if _is_admin_only_request(request):
        return JSONResponse({"detail": "admin access required"}, status_code=403)

    if path == "/":
        view = request.query_params.get("view") or ""
        has_resource = bool(request.query_params.get("project") or request.query_params.get("repo"))
        if (not view and not has_resource) or view in {"productivity", "cerebro", "code-search", "logs"}:
            workspace = first_allowed_workspace(row)
            if workspace is None:
                return _no_workspace_page(row)
            return RedirectResponse(
                url=f"/?view=workspace&workspace={quote(workspace, safe='')}", status_code=303,
            )

    if pseudo is not None:
        return JSONResponse({"detail": "admin access required"}, status_code=403)
    if workspace:
        if not can_access_workspace(row, workspace):
            return JSONResponse({"detail": "workspace not found"}, status_code=404)
        return await call_next(request)
    if resource:
        owner = workspace_id_for_path(resource)
        if owner == HOME_WORKSPACE:
            return JSONResponse({"detail": "admin access required"}, status_code=403)
        if owner is None or not can_access_workspace(row, owner):
            return JSONResponse({"detail": "resource not found"}, status_code=404)
        return await call_next(request)

    if request.method == "GET" and path == "/api/term/sessions" and not request.query_params.get("project_id"):
        return await call_next(request)
    if path in _GLOBAL_FILTERED_GETS or path in _GLOBAL_USER_ENDPOINTS:
        return await call_next(request)

    default_workspace = first_allowed_workspace(row)
    default_root = workspace_root_for_id(default_workspace) if default_workspace else None
    if default_root is not None:
        request.state.auth_workspace_root = default_root
        return await call_next(request)
    return JSONResponse({"detail": "workspace not found"}, status_code=404)
