"""Project-local notebook runtime configuration and environment builds.

Lab owns the Jupyter control plane, but a project owns the Python interpreter,
packages, editable libraries, CLI search path, and process environment used by
its kernels.  The desired configuration is stored as ``runtime.json`` in the
project; generated environments and build state live under
``<workspace>/.lab/state/runtimes`` so they never dirty the project tree.

There are two runtime kinds:

``managed``
    Build an isolated venv from a selected Python interpreter and install
    ipykernel plus the configured packages/editable libraries.

``existing``
    Use an existing interpreter verbatim.  Build/validation verifies that it
    can import ipykernel but never mutates it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RUNTIME_FILENAME = "runtime.json"
RUNTIME_VERSION = 1
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_build_locks: dict[str, threading.Lock] = {}
_build_locks_guard = threading.Lock()


class RuntimeConfigError(ValueError):
    """The desired runtime configuration is invalid for this workspace."""


class RuntimeBuildError(RuntimeError):
    """A runtime command or validation step failed."""

    def __init__(self, detail: str, *, log: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.log = log


class RuntimeCliCheck(BaseModel):
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=lambda: ["--version"])
    timeout: int = Field(default=30, ge=1, le=300)

    @field_validator("command")
    @classmethod
    def _plain_command(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value or "\n" in value:
            raise ValueError("CLI command must be one non-empty executable name or path")
        return value


class ProjectRuntimeSpec(BaseModel):
    version: int = Field(default=RUNTIME_VERSION, ge=1)
    mode: Literal["local", "darwin"] = "local"
    kind: Literal["managed", "existing"] = "managed"
    python: str = ""
    packages: list[str] = Field(default_factory=list)
    editable: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    cli_paths: list[str] = Field(default_factory=list)
    cli_checks: list[RuntimeCliCheck] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    working_dir: str = "."
    validation_code: str = ""

    @field_validator("python", "working_dir")
    @classmethod
    def _no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("runtime path contains a NUL byte")
        return value.strip()

    @field_validator("packages")
    @classmethod
    def _package_specs(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if not value:
                continue
            if value.startswith("-") or "\x00" in value or "\n" in value:
                raise ValueError(f"invalid package specification: {value!r}")
            cleaned.append(value)
        return cleaned

    @field_validator("editable", "imports", "cli_paths")
    @classmethod
    def _string_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if value and "\x00" not in value and "\n" not in value:
                cleaned.append(value)
        return cleaned


class RuntimeHandle(BaseModel):
    project_id: str
    fingerprint: str
    python: str
    working_dir: str
    environment: dict[str, str]
    display_name: str


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _atomic_json(target: Path, data: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def project_for_notebook(root: Path, rel_path: str) -> tuple[str, Path]:
    parts = Path(rel_path).parts
    if len(parts) < 3 or parts[0] != "projects":
        raise RuntimeConfigError("notebook must live under projects/<id>/")
    project_id = parts[1]
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise RuntimeConfigError("invalid project id in notebook path")
    project_dir = (root / "projects" / project_id).resolve()
    root_resolved = root.resolve()
    if root_resolved not in project_dir.parents:
        raise RuntimeConfigError("project path escapes workspace")
    return project_id, project_dir


def runtime_config_path(root: Path, rel_path: str) -> Path:
    _, project_dir = project_for_notebook(root, rel_path)
    return project_dir / RUNTIME_FILENAME


def load_runtime_spec(root: Path, rel_path: str) -> ProjectRuntimeSpec | None:
    target = runtime_config_path(root, rel_path)
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return ProjectRuntimeSpec.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeConfigError(f"invalid {RUNTIME_FILENAME}: {exc}") from exc


def save_runtime_spec(root: Path, rel_path: str, spec: ProjectRuntimeSpec) -> Path:
    target = runtime_config_path(root, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(target, spec.model_dump(mode="json"))
    return target


def runtime_fingerprint(spec: ProjectRuntimeSpec) -> str:
    payload = json.dumps(
        spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _project_state_dir(root: Path, project_id: str) -> Path:
    return root / ".lab" / "state" / "runtimes" / project_id


def _build_dir(root: Path, project_id: str, fingerprint: str) -> Path:
    return _project_state_dir(root, project_id) / fingerprint


def _active_path(root: Path, project_id: str) -> Path:
    return _project_state_dir(root, project_id) / "active.json"


def _last_build_path(root: Path, project_id: str) -> Path:
    return _project_state_dir(root, project_id) / "last-build.json"


def _lock_for(root: Path, project_id: str) -> threading.Lock:
    key = str((_project_state_dir(root, project_id)).resolve())
    with _build_locks_guard:
        lock = _build_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _build_locks[key] = lock
        return lock


def _resolve_python(selector: str) -> Path:
    selector = selector.strip()
    candidates: list[str] = []
    if not selector:
        candidates.append(sys.executable)
    elif os.path.sep in selector or (os.path.altsep and os.path.altsep in selector):
        candidates.append(selector)
    elif re.fullmatch(r"\d+\.\d+(?:\.\d+)?", selector):
        major_minor = ".".join(selector.split(".")[:2])
        candidates.extend([f"python{selector}", f"python{major_minor}"])
    else:
        candidates.append(selector)

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            resolved = shutil.which(candidate)
            if resolved:
                path = Path(resolved)
        if path.is_file() and os.access(path, os.X_OK):
            # A venv's Python is commonly a symlink to the system binary.
            # Resolving it discards pyvenv.cfg discovery and therefore loses
            # the venv's installed ipykernel and client libraries.
            return Path(os.path.abspath(path))
    shown = selector or sys.executable
    raise RuntimeBuildError(f"Python interpreter not found: {shown}")


def _resolve_runtime_path(project_dir: Path, value: str) -> Path:
    """Resolve a client-owned host path, relative to the project by default.

    Absolute paths are intentionally supported: an existing environment,
    editable SDK, CLI installation, or data working directory may live outside
    the Lab workspace on the client's machine.
    """
    raw = Path(value).expanduser()
    target = raw.resolve() if raw.is_absolute() else (project_dir / raw).resolve()
    return target


def _working_dir(root: Path, project_dir: Path, spec: ProjectRuntimeSpec) -> Path:
    target = _resolve_runtime_path(project_dir, spec.working_dir or ".")
    if not target.is_dir():
        raise RuntimeBuildError(f"working directory does not exist: {spec.working_dir}")
    return target


def _runtime_environment(
    root: Path,
    project_dir: Path,
    spec: ProjectRuntimeSpec,
    python: Path,
) -> dict[str, str]:
    env = dict(os.environ)
    path_entries = [str(python.parent)]
    for raw in spec.cli_paths:
        path_entries.append(str(_resolve_runtime_path(project_dir, raw)))
    inherited_path = env.get("PATH", "")
    if inherited_path:
        path_entries.append(inherited_path)
    env["PATH"] = os.pathsep.join(path_entries)
    env.update({str(k): str(v) for k, v in spec.environment.items()})
    return env


def _run_logged(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    log: list[str],
    timeout: int = 900,
) -> None:
    log.append("$ " + " ".join(command))
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeBuildError(f"runtime command failed: {exc}", log="\n".join(log)) from exc
    if proc.stdout:
        log.append(proc.stdout.rstrip())
    if proc.stderr:
        log.append(proc.stderr.rstrip())
    if proc.returncode != 0:
        raise RuntimeBuildError(
            f"runtime command exited {proc.returncode}: {' '.join(command[:3])}",
            log="\n".join(log),
        )


def _validation_source(spec: ProjectRuntimeSpec) -> str:
    checks = [
        "import json, os, shutil, subprocess, sys",
        "result = {'python': sys.executable, 'imports': {}, 'clis': {}}",
    ]
    for module in spec.imports:
        checks.extend([
            f"__import__({module!r})",
            f"result['imports'][{module!r}] = 'ok'",
        ])
    for cli in spec.cli_checks:
        command = cli.command
        checks.extend([
            f"resolved = shutil.which({command!r})",
            f"assert resolved, {('CLI not found on kernel PATH: ' + command)!r}",
            (
                "completed = subprocess.run("
                f"[{command!r}, *{cli.args!r}], capture_output=True, text=True, "
                f"timeout={cli.timeout}, check=True)"
            ),
            (
                f"result['clis'][{command!r}] = {{'path': resolved, "
                "'stdout': completed.stdout[-1000:], 'stderr': completed.stderr[-1000:]}"
            ),
        ])
    if spec.validation_code.strip():
        checks.append(spec.validation_code)
    checks.append("print('__LAB_RUNTIME_VALIDATION__' + json.dumps(result, sort_keys=True))")
    return "\n".join(checks)


def _state_handle(root: Path, rel_path: str, data: dict[str, Any]) -> RuntimeHandle:
    spec = load_runtime_spec(root, rel_path)
    if spec is None:
        raise RuntimeBuildError("project runtime configuration is missing")
    _, project_dir = project_for_notebook(root, rel_path)
    python = Path(str(data["python"]))
    return RuntimeHandle.model_validate({
        "project_id": data["project_id"],
        "fingerprint": data["fingerprint"],
        "python": str(python),
        "working_dir": data["working_dir"],
        # Inherit the server process environment at kernel-start time instead
        # of persisting it in state.json (which could copy credentials into a
        # project-readable API response). Only the user's explicit overrides
        # and computed PATH are persisted indirectly via runtime.json.
        "environment": _runtime_environment(root, project_dir, spec, python),
        "display_name": data.get("display_name") or data["project_id"],
    })


def _validate_handle(
    handle: RuntimeHandle,
    spec: ProjectRuntimeSpec,
    *,
    log: list[str],
) -> dict[str, Any]:
    # Validate through the exact same Jupyter messaging path used by notebook
    # cells. Importing in the Lab backend would miss kernel PATH/interpreter
    # problems, especially for libraries invoking CLIs.
    from core.notebook_kernel import execute_ephemeral  # local import avoids cycle

    validation = execute_ephemeral(handle, _validation_source(spec), timeout=120)
    errors = [
        out for out in validation["cell_outputs"]
        if out.get("output_type") == "error"
    ]
    if errors:
        error_text = "\n".join(
            str(out.get("evalue") or "runtime validation error") for out in errors
        )
        raise RuntimeBuildError(error_text, log="\n".join(log))
    return validation


def build_runtime(root: Path, rel_path: str) -> dict[str, Any]:
    """Materialize and validate the desired project runtime synchronously."""
    spec = load_runtime_spec(root, rel_path)
    if spec is None:
        raise RuntimeBuildError(f"configure {RUNTIME_FILENAME} before building")
    if spec.mode != "local":
        raise RuntimeBuildError("only local runtimes are built by Lab")

    project_id, project_dir = project_for_notebook(root, rel_path)
    fingerprint = runtime_fingerprint(spec)
    project_state = _project_state_dir(root, project_id)
    final_dir = _build_dir(root, project_id, fingerprint)
    active_path = _active_path(root, project_id)
    log: list[str] = []

    with _lock_for(root, project_id):
        ready_state = final_dir / "state.json"
        if ready_state.is_file():
            try:
                data = json.loads(ready_state.read_text(encoding="utf-8"))
                if data.get("status") == "ready":
                    # Build & validate must not return a stale green check if a
                    # host CLI or existing environment changed in place.
                    try:
                        data["validation"] = _validate_handle(
                            _state_handle(root, rel_path, data), spec, log=log
                        )
                        data["validated_at"] = _utc_now()
                    except RuntimeBuildError as exc:
                        failed = {
                            **data,
                            "status": "broken",
                            "finished_at": _utc_now(),
                            "detail": exc.detail,
                            "log": (exc.log or "\n".join(log))[-20000:],
                        }
                        _atomic_json(active_path, failed)
                        _atomic_json(_last_build_path(root, project_id), failed)
                        raise
                    _atomic_json(ready_state, data)
                    _atomic_json(active_path, data)
                    _atomic_json(_last_build_path(root, project_id), data)
                    return data
            except (OSError, json.JSONDecodeError):
                pass

        project_state.mkdir(parents=True, exist_ok=True)
        temp_dir = project_state / f".build-{fingerprint}-{os.getpid()}-{threading.get_ident()}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        building = {
            "status": "building",
            "project_id": project_id,
            "fingerprint": fingerprint,
            "started_at": _utc_now(),
            "spec": spec.model_dump(mode="json"),
        }
        _atomic_json(_last_build_path(root, project_id), building)

        try:
            base_python = _resolve_python(spec.python)
            if spec.kind == "existing":
                runtime_python = base_python
            else:
                venv_dir = temp_dir / "venv"
                _run_logged(
                    [str(base_python), "-m", "venv", str(venv_dir)],
                    cwd=project_dir,
                    env=None,
                    log=log,
                )
                runtime_python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                install = [
                    str(runtime_python), "-m", "pip", "install",
                    "ipykernel>=6.29,<8", *spec.packages,
                ]
                _run_logged(install, cwd=project_dir, env=None, log=log)
                for raw in spec.editable:
                    editable = _resolve_runtime_path(project_dir, raw)
                    _run_logged(
                        [str(runtime_python), "-m", "pip", "install", "-e", str(editable)],
                        cwd=project_dir,
                        env=None,
                        log=log,
                    )

            working_dir = _working_dir(root, project_dir, spec)
            environment = _runtime_environment(root, project_dir, spec, runtime_python)

            validation = _validate_handle(
                RuntimeHandle(
                    project_id=project_id,
                    fingerprint=fingerprint,
                    python=str(runtime_python),
                    working_dir=str(working_dir),
                    environment=environment,
                    display_name=f"{project_id} · Python",
                ),
                spec,
                log=log,
            )

            if spec.kind == "managed":
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                if final_dir.exists():
                    shutil.rmtree(final_dir)
                os.replace(temp_dir, final_dir)
                runtime_python = final_dir / "venv" / (
                    "Scripts/python.exe" if os.name == "nt" else "bin/python"
                )
                environment = _runtime_environment(root, project_dir, spec, runtime_python)
            else:
                final_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "status": "ready",
                "project_id": project_id,
                "fingerprint": fingerprint,
                "python": str(runtime_python),
                "working_dir": str(working_dir),
                "display_name": f"{project_id} · Python",
                "built_at": _utc_now(),
                "spec": spec.model_dump(mode="json"),
                "validation": validation,
                "log": "\n".join(log)[-20000:],
            }
            _atomic_json(final_dir / "state.json", data)
            _atomic_json(active_path, data)
            _atomic_json(_last_build_path(root, project_id), data)
            return data
        except Exception as exc:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if isinstance(exc, RuntimeBuildError):
                detail = exc.detail
                build_log = exc.log or "\n".join(log)
            else:
                detail = str(exc)
                build_log = "\n".join(log)
            failed = {
                **building,
                "status": "broken",
                "finished_at": _utc_now(),
                "detail": detail,
                "log": build_log[-20000:],
            }
            _atomic_json(_last_build_path(root, project_id), failed)
            raise RuntimeBuildError(detail, log=build_log) from exc


def runtime_status(root: Path, rel_path: str) -> dict[str, Any]:
    project_id, _ = project_for_notebook(root, rel_path)
    spec = load_runtime_spec(root, rel_path)
    desired = runtime_fingerprint(spec) if spec is not None else None
    active: dict[str, Any] | None = None
    last_build: dict[str, Any] | None = None
    try:
        active = json.loads(_active_path(root, project_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    try:
        last_build = json.loads(_last_build_path(root, project_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    if spec is None:
        status = "legacy"
    elif spec.mode == "darwin":
        status = "darwin"
    elif active and active.get("status") == "ready" and active.get("fingerprint") == desired:
        status = "ready"
    elif last_build and last_build.get("status") == "broken" and last_build.get("fingerprint") == desired:
        status = "broken"
    elif active:
        status = "update_available"
    else:
        status = "draft"
    return {
        "project_id": project_id,
        "configured": spec is not None,
        "spec": spec.model_dump(mode="json") if spec is not None else None,
        "desired_fingerprint": desired,
        "active_fingerprint": active.get("fingerprint") if active else None,
        "status": status,
        "active": active,
        "last_build": last_build,
    }


def active_runtime(root: Path, rel_path: str) -> RuntimeHandle | None:
    spec = load_runtime_spec(root, rel_path)
    if spec is None or spec.mode != "local":
        return None
    project_id, _ = project_for_notebook(root, rel_path)
    desired = runtime_fingerprint(spec)
    try:
        data = json.loads(_active_path(root, project_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeBuildError("project runtime is not built") from exc
    if data.get("status") != "ready" or data.get("fingerprint") != desired:
        raise RuntimeBuildError("project runtime has changed; build it before running cells")
    return _state_handle(root, rel_path, data)
