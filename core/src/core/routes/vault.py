from __future__ import annotations

from lab import naming

import json
import os
import hashlib
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import paths
from lab import settings as lab_settings

from core import auth, fsguard
from core import vault_config
from core.diff_parser import get_registered_repos


router = APIRouter()


class VaultUseRequest(BaseModel):
    id: str | None = None
    path: str | None = None


class VaultAgentsPatch(BaseModel):
    supported: list[str]
    vault: str | None = None


class VaultAppearancePatch(BaseModel):
    name: str
    color: str


class VaultCreateRequest(BaseModel):
    path: str
    name: str | None = None
    create: bool = False


def _vault_id_for(root: Path, rows: list[dict]) -> str:
    resolved = root.expanduser().resolve()
    for row in rows:
        try:
            if Path(str(row["path"])).expanduser().resolve() == resolved:
                return str(row["id"])
        except (OSError, KeyError):
            continue
    return resolved.name


def _vault_row(root: Path, rows: list[dict]) -> dict:
    resolved = root.expanduser().resolve()
    vault_id = _vault_id_for(resolved, rows)
    for row in rows:
        try:
            if Path(str(row["path"])).expanduser().resolve() == resolved:
                return {
                    "id": str(row["id"]),
                    "name": str(row.get("name") or row["id"]),
                    "path": str(resolved),
                    "active": True,
                    "exists": resolved.is_dir(),
                }
        except (OSError, KeyError):
            continue
    return {
        "id": vault_id,
        "name": resolved.name,
        "path": str(resolved),
        "active": True,
        "exists": resolved.is_dir(),
    }


def _payload(request: Request) -> dict:
    current_root = auth.request_root(request)
    data = paths.read_vault_registry()
    rows = list(data.get("vaults") or [])
    current = _vault_row(current_root, rows)

    seen: set[str] = set()
    vaults: list[dict] = []
    for row in rows:
        try:
            root = Path(str(row["path"])).expanduser().resolve()
        except OSError:
            root = Path(str(row["path"])).expanduser()
        key = str(root)
        seen.add(key)
        vaults.append({
            "id": str(row["id"]),
            "name": str(row.get("name") or row["id"]),
            "path": key,
            "active": key == current["path"],
            "exists": root.is_dir(),
        })
    if current["path"] not in seen:
        vaults.insert(0, current)
    user = auth.require_user(request)
    if not auth.is_admin(user):
        vaults = [
            row for row in vaults
            if auth.can_access_vault(user, str(row.get("id") or ""))
        ]
        visible_active = current["id"] if any(row["id"] == current["id"] for row in vaults) else None
        if visible_active is None and vaults:
            visible_active = vaults[0]["id"]
        for row in vaults:
            row["active"] = row["id"] == visible_active
        current = next((row for row in vaults if row["id"] == visible_active), None)
    # Advisory vault.json status for the ACTIVE vault only. Other
    # registered roots may live on unplugged volumes; reading a file there
    # would hang the whole dashboard, so they are not touched here.
    try:
        config_root = Path(str(current["path"])).expanduser().resolve() if current else None
        if config_root is not None:
            current["config"] = fsguard.guarded(
                config_root,
                vault_config.summarize_vault_config,
                config_root,
            )
    except HTTPException:
        pass
    return {
        "active": current["id"] if current else None,
        "current": current,
        "vaults": vaults,
    }


def _resolve_requested_vault(body: VaultUseRequest) -> Path:
    if body.id:
        data = paths.read_vault_registry()
        for row in data.get("vaults") or []:
            if str(row.get("id")) == body.id:
                return Path(str(row["path"])).expanduser().resolve()
        raise HTTPException(status_code=404, detail=f"vault {body.id!r} not found")
    if body.path:
        return Path(body.path).expanduser().resolve()
    raise HTTPException(status_code=400, detail="vault id or path required")


def _validate_vault(root: Path) -> None:
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"vault path not found: {root}")
    if not (root / "lab.toml").is_file() and not (root / "content").is_dir():
        raise HTTPException(status_code=400, detail=f"{root} is not a Lab vault")


def _vault_root(request: Request, vault: str | None = None) -> Path:
    active_root = auth.request_root(request)
    if not vault:
        return active_root
    for row in _payload(request)["vaults"]:
        if row["id"] == vault:
            root = Path(str(row["path"])).expanduser().resolve()
            _validate_vault(root)
            return root
    raise HTTPException(status_code=404, detail=f"vault {vault!r} not found")


_VAULT_COLORS = (
    "#58a6ff", "#a371f7", "#3fb950", "#d29922",
    "#f78166", "#db61a2", "#39c5cf", "#8b949e",
)


def _default_vault_color(vault_id: str) -> str:
    digest = hashlib.sha1(vault_id.encode("utf-8")).digest()
    return _VAULT_COLORS[int.from_bytes(digest, "big") % len(_VAULT_COLORS)]


def _vault_overview(root: Path, fallback_name: str, vault_id: str) -> dict:
    workspaces = _scan_workspace_ids(root)
    loaded = vault_config.load_vault_config(root)
    doc = loaded.get("config") if isinstance(loaded.get("config"), dict) else {}
    display = doc.get("display") if isinstance(doc.get("display"), dict) else {}
    name = doc.get("name") if isinstance(doc.get("name"), str) and doc.get("name").strip() else fallback_name
    color = display.get("color") if isinstance(display.get("color"), str) else _default_vault_color(vault_id)

    workspace_rows: list[dict] = []
    for workspace in get_registered_repos(root):
        repos = [
            {"path": repo, "name": Path(repo).name, "branch": ""}
            for repo in (workspace.get("repos") or [])
        ]
        workspace_rows.append({
            **workspace,
            "repos": repos,
            "vault": vault_id,
            "vault_name": name,
            "vault_color": color,
            "vault_path": str(root),
        })
    return {
        "workspaces": workspaces,
        "workspace_rows": workspace_rows,
        "name": name,
        "color": color,
        "config": {
            "present": loaded["present"],
            "valid": loaded["valid"],
            "errors": loaded["errors"],
            "warnings": loaded["warnings"],
        },
    }


@router.get("/api/vaults")
def list_vaults(request: Request) -> dict:
    return _payload(request)


@router.post("/api/vaults")
def add_vault(body: VaultCreateRequest, request: Request) -> dict:
    """Register an existing vault or create an empty one via ``lab init``."""
    auth.require_admin(request)
    root = Path(body.path).expanduser().resolve()
    display_name = (body.name or root.name).strip() or root.name
    previous_active = paths.active_vault()
    if body.create:
        if (root / "lab.toml").exists():
            raise HTTPException(status_code=409, detail="vault already exists; add it as existing")
        env = dict(os.environ)
        env.pop("LAB_VAULT", None)
        env.pop("LAB_ROOT", None)
        proc = subprocess.run(
            [sys.executable, "-m", "lab", "init", str(root), "--name", display_name, "--no-example"],
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().removeprefix("Error: ")
            raise HTTPException(status_code=400, detail=detail or "could not create vault")
        if previous_active is not None:
            paths.register_vault(previous_active, active=True)
    else:
        _validate_vault(root)
    row = paths.register_vault(root, name=display_name, active=False)
    return {"vault": row, **_payload(request)}


@router.get("/api/vault/config")
def get_vault_config(request: Request, vault: str | None = None) -> dict:
    """Full vault.json load result (parsed document + validation) for the
    active vault. The file is optional; ``present: false`` is a normal,
    valid answer."""
    root = _vault_root(request, vault)
    def load() -> dict:
        return {"root": str(root), "source": naming.vault_config_file(root).name,
                **vault_config.load_vault_config(root)}
    return fsguard.guarded(root, load)


def _vault_agent_policy(root: Path) -> dict:
    supported = vault_config.supported_agents(root)
    default = lab_settings.resolve_agent(root)
    if default not in supported:
        default = supported[0]
    return {
        "root": str(root),
        "supported": supported,
        "default": default,
    }


@router.get("/api/vault/agents")
def get_vault_agents(request: Request, vault: str | None = None) -> dict:
    """Return the effective agent choices for the active vault."""
    root = _vault_root(request, vault)
    return fsguard.guarded(root, _vault_agent_policy, root)


def _write_starter_vault_config(root: Path) -> None:
    """Write a minimal valid vault.json reflecting the vault's
    current identity and agent settings. Atomic; never overwrites."""
    rows = list(paths.read_vault_registry().get("vaults") or [])
    row = _vault_row(root, rows)
    settings = lab_settings.load(root)
    doc = {
        "version": 1,
        "id": row["id"],
        "name": row["name"],
        "agents": {
            "supported": list(lab_settings.VALID_AGENTS),
            "default": settings.get("defaultAgent") or lab_settings.DEFAULT_AGENT,
        },
    }
    path = root / "vault.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_vault_agents(root: Path, supported: list[str]) -> dict:
    if not (naming.vault_config_file(root)).exists():
        _write_starter_vault_config(root)
    vault_config.update_supported_agents(
        root,
        supported,
        lab_settings.resolve_agent(root),
    )
    return _vault_agent_policy(root)


@router.post("/api/vault/agents")
def update_vault_agents(body: VaultAgentsPatch, request: Request) -> dict:
    """Replace the active vault's enabled-agent set.

    The rest of ``vault.json`` is preserved. The last enabled agent cannot
    be removed because every terminal menu needs a valid fallback.
    """
    root = _vault_root(request, body.vault)
    try:
        return fsguard.guarded(
            root,
            _write_vault_agents,
            root,
            body.supported,
        )
    except vault_config.VaultConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/vault/config/init")
def init_vault_config(request: Request, vault: str | None = None) -> dict:
    """Create a starter vault.json at the active vault root.

    Bootstrap only: 409 when the file already exists — edits and the real
    configuration work belong to the user's agent (the Vault tab's
    setup prompt explains the structure to it)."""
    root = _vault_root(request, vault)
    if (naming.vault_config_file(root)).exists():
        raise HTTPException(status_code=409, detail="vault.json already exists")
    fsguard.guarded(root, _write_starter_vault_config, root)
    result = fsguard.guarded(root, vault_config.load_vault_config, root)
    return {"root": str(root), **result}


@router.patch("/api/vaults/{vault_id}/appearance")
def update_vault_appearance(
    vault_id: str, body: VaultAppearancePatch, request: Request,
) -> dict:
    root = _vault_root(request, vault_id)
    try:
        result = fsguard.guarded(
            root, vault_config.update_appearance, root, body.name, body.color,
        )
    except vault_config.VaultConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = result.get("config") or {}
    display = doc.get("display") if isinstance(doc.get("display"), dict) else {}
    return {
        "id": vault_id,
        "name": doc.get("name") or vault_id,
        "color": display.get("color") or _default_vault_color(vault_id),
        "path": str(root),
    }


@router.post("/api/vaults/use")
def use_vault(body: VaultUseRequest, request: Request) -> dict:
    auth.require_admin(request)
    root = _resolve_requested_vault(body)
    _validate_vault(root)
    paths.register_vault(root, name=root.name, active=True)
    request.app.state.switch_vault(root)
    return _payload(request)


def _scan_workspace_ids(root: Path) -> list[str]:
    """List workspace directory names under ``root/workspaces``.

    Runs entirely inside ``fsguard.guarded()`` -- including the ``is_dir()``
    check -- so a stalled/wedged volume can't hang on that first stat call
    either; only ``guarded()``'s timeout ever gets to observe it.
    """
    workspaces_dir = naming.workspaces_dir(root)
    if not workspaces_dir.is_dir():
        return []
    return sorted(
        p.name for p in workspaces_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


@router.get("/api/vaults/workspaces")
def list_vault_workspaces(request: Request) -> dict:
    """All registered vaults, each with its workspace ids.

    One dead/stalled volume must not blank the whole dashboard: a per-
    vault scan that fails with fsguard's 503 is caught here and turned
    into ``unavailable: true`` (empty ``workspaces``) for that entry only,
    while every other vault's listing still comes back normally.
    """
    payload = _payload(request)
    vaults: list[dict] = []
    for row in payload["vaults"]:
        entry = dict(row)
        root = Path(str(row["path"]))
        try:
            overview = fsguard.guarded(
                root, _vault_overview, root, entry["name"], entry["id"],
            )
            entry.update(overview)
            entry["unavailable"] = False
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            entry["workspaces"] = []
            entry["workspace_rows"] = []
            entry["color"] = _default_vault_color(entry["id"])
            entry["unavailable"] = True
            entry["detail"] = exc.detail
        vaults.append(entry)
    return {"active": payload["active"], "vaults": vaults}


@router.get("/api/vaults/resources")
def vault_workspace_resources(request: Request, vault: str) -> dict:
    """Live resource counts, independent of which workspace tabs are open."""
    from core import notebook_kernel
    from core.routes import servers, term

    auth.require_vault(request, vault)
    root = _vault_root(request, vault)
    terminals = fsguard.guarded(root, term._sessions_for_root, root, None, include_agent_details=False)
    server_rows = [row for row in servers.list_servers(request)["servers"] if row["vault"] == vault]
    # A managed server owns a tmux session; count that process as a server once.
    server_sessions = {row["session_name"] for row in server_rows if row.get("session_name")}
    live_terminal_names = {row["name"] for row in terminals}
    counts: dict[str, dict[str, int]] = {}

    def add(workspace_id: str | None, resource: str) -> None:
        if not workspace_id or workspace_id.startswith("__"):
            return
        counts.setdefault(workspace_id, {"terminals": 0, "servers": 0, "kernels": 0})[resource] += 1

    for row in terminals:
        if row["name"] not in server_sessions:
            add(row.get("workspace_id"), "terminals")
    for row in server_rows:
        if row.get("session_name") in live_terminal_names or row["status"] in {"running", "external", "starting", "unhealthy"}:
            add(row["workspace_id"], "servers")
    workspace_root = naming.workspaces_dir(root).resolve()
    for path in notebook_kernel.live_notebook_paths(root):
        try:
            relative = (root / path).resolve().relative_to(workspace_root)
        except ValueError:
            continue
        if len(relative.parts) > 1:
            add(relative.parts[0], "kernels")
    return {"vault": vault, "workspaces": counts}
