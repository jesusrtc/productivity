from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from lab import paths

from core import auth


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


class LoginBody(BaseModel):
    username: str
    password: str


class NewUserBody(BaseModel):
    username: str
    name: str | None = None
    role: str = "user"
    password: str
    workspaces: list[str] = Field(default_factory=list)


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    password: str | None = None
    workspaces: list[str] | None = None
    disabled: bool | None = None


def _known_workspace_ids() -> set[str]:
    return {
        str(row.get("id"))
        for row in paths.read_workspace_registry().get("workspaces") or []
        if row.get("id")
    }


def _validated_workspaces(values: list[str]) -> list[str]:
    known = _known_workspace_ids()
    requested = sorted({str(value) for value in values if value})
    missing = [value for value in requested if value not in known]
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown workspace: {missing[0]}")
    return requested


def _admin_count(users: list[dict]) -> int:
    return sum(1 for row in users if row.get("role") == "admin" and not row.get("disabled"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.user_from_connection(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.post("/api/auth/login")
def login(body: LoginBody) -> JSONResponse:
    row = auth.authenticate(body.username, body.password)
    if row is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    response = JSONResponse({"authenticated": True, "user": auth.public_user(row)})
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.issue_session(row),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return response


@router.get("/api/auth/me")
def me(request: Request) -> dict:
    row = auth.require_user(request)
    return {"authenticated": True, "user": auth.public_user(row)}


@router.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("/api/admin/users")
def list_users(request: Request) -> dict:
    auth.require_admin(request)
    store = auth.load_store()
    rows = sorted((auth.public_user(row) for row in store.get("users") or []), key=lambda row: row["name"].lower())
    return {"users": rows}


@router.post("/api/admin/users")
def create_user(body: NewUserBody, request: Request) -> dict:
    auth.require_admin(request)
    try:
        username = auth.normalize_username(body.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="role must be admin or user")
    if not body.password:
        raise HTTPException(status_code=400, detail="password is required")
    with auth._LOCK:
        store = auth.load_store()
        if any(row.get("username") == username for row in store.get("users") or []):
            raise HTTPException(status_code=409, detail="user already exists")
        row = {
            "username": username,
            "name": (body.name or username.title()).strip() or username.title(),
            "role": body.role,
            "password_sha256": auth.password_sha256(body.password),
            "workspaces": _validated_workspaces(body.workspaces),
            "disabled": False,
        }
        store.setdefault("users", []).append(row)
        auth.save_store(store)
    return {"user": auth.public_user(row)}


@router.patch("/api/admin/users/{username}")
def update_user(username: str, body: UserPatch, request: Request) -> dict:
    auth.require_admin(request)
    try:
        wanted = auth.normalize_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.role is not None and body.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="role must be admin or user")
    with auth._LOCK:
        store = auth.load_store()
        row = next((item for item in store.get("users") or [] if item.get("username") == wanted), None)
        if row is None:
            raise HTTPException(status_code=404, detail="user not found")
        would_remove_admin = (
            row.get("role") == "admin"
            and not row.get("disabled")
            and (body.role == "user" or body.disabled is True)
        )
        if would_remove_admin and _admin_count(store["users"]) <= 1:
            raise HTTPException(status_code=400, detail="at least one enabled admin is required")
        if body.name is not None:
            row["name"] = body.name.strip() or wanted.title()
        if body.role is not None:
            row["role"] = body.role
        if body.password is not None:
            if not body.password:
                raise HTTPException(status_code=400, detail="password cannot be empty")
            row["password_sha256"] = auth.password_sha256(body.password)
        if body.workspaces is not None:
            row["workspaces"] = _validated_workspaces(body.workspaces)
        if body.disabled is not None:
            row["disabled"] = body.disabled
        auth.save_store(store)
    return {"user": auth.public_user(row)}
