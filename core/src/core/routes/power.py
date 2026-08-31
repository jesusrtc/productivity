"""Timed macOS lid-closed wake control.

The browser Wake Lock API used by Lab's existing Keep Alive switch cannot
prevent a Mac from sleeping after its lid closes.  This route deliberately
uses macOS's system setting instead, authenticated through sudo with either
the user's configured Touch ID flow or a one-time password from the UI.

The privileged helper reads a user-owned deadline file once per second.  That
keeps renewal cheap (only the deadline changes), survives a Lab server restart,
and guarantees that the helper restores normal sleep when the deadline expires.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, SecretStr

from core import auth


router = APIRouter()

_ALLOWED_MINUTES = {15, 30, 60}
_APPROVAL_TIMEOUT_S = 120
_SUCCESS_MARKER = "__LAB_LID_AWAKE_STARTED__"
_LOCK = threading.Lock()


class LidAwakeRequest(BaseModel):
    minutes: Literal[15, 30, 60]
    auth_method: Literal["touch_id", "password"] = "touch_id"
    password: SecretStr | None = None


def _deadline_path() -> Path:
    """One system-wide timer per logged-in user, shared across Lab checkouts."""
    return Path(tempfile.gettempdir()) / f"lab-lid-awake-{os.getuid()}.deadline"


def _is_supported() -> bool:
    return (
        sys.platform == "darwin"
        and Path("/usr/bin/pmset").is_file()
        and Path("/usr/bin/script").is_file()
        and Path("/usr/bin/sudo").is_file()
    )


def _read_deadline() -> int | None:
    try:
        raw = _deadline_path().read_text(encoding="utf-8").strip()
        deadline = int(raw)
    except (OSError, ValueError):
        return None
    return deadline if deadline > 0 else None


def _write_deadline(deadline: int) -> None:
    """Atomically replace the deadline so the privileged reader never sees a partial value."""
    path = _deadline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(f"{deadline}\n", encoding="utf-8")
    os.replace(temporary, path)


def _clear_deadline() -> None:
    try:
        _deadline_path().unlink(missing_ok=True)
    except OSError:
        # If removal fails, replace the value with an already-expired deadline
        # so the root helper still restores ordinary sleep within one second.
        try:
            _write_deadline(int(time.time()) - 1)
        except OSError:
            pass


def _status(*, now: int | None = None) -> dict:
    current = int(time.time() if now is None else now)
    deadline = _read_deadline()
    active = bool(deadline and deadline > current)
    if deadline is not None and not active:
        _clear_deadline()
    return {
        "supported": _is_supported(),
        "active": active,
        "deadline": deadline if active else None,
        "remaining_seconds": max(0, deadline - current) if active and deadline else 0,
    }


def _timer_helper_command(deadline_file: Path) -> str:
    """Return the fixed command that sudo runs as root."""
    path = shlex.quote(str(deadline_file))
    loop = (
        "trap '/usr/bin/pmset -a disablesleep 0' EXIT HUP INT TERM\n"
        "while :; do\n"
        f"  deadline=$(/bin/cat {path} 2>/dev/null) || break\n"
        "  case \"$deadline\" in ''|*[!0-9]*) break ;; esac\n"
        "  now=$(/bin/date +%s)\n"
        "  [ \"$deadline\" -gt \"$now\" ] || break\n"
        "  /bin/sleep 1\n"
        "done\n"
    )
    # pmset runs in the foreground, then the small deadline watcher detaches.
    # A fixed marker is printed only after both steps succeed; macOS `script`
    # always exits zero, so the caller uses this marker as its success signal.
    return (
        "/usr/bin/pmset -a disablesleep 1; "
        "status=$?; [ \"$status\" -eq 0 ] || exit \"$status\"; "
        f"/usr/bin/nohup /bin/sh -c {shlex.quote(loop)} "
        f"</dev/null >/dev/null 2>&1 & /bin/echo {_SUCCESS_MARKER}"
    )


def _start_privileged_timer(
    *, auth_method: Literal["touch_id", "password"], password: str | None = None,
) -> None:
    command = _timer_helper_command(_deadline_path())
    if auth_method == "password":
        argv = [
            "/usr/bin/sudo", "-S", "-p", "",
            "--", "/bin/sh", "-c", command,
        ]
        stdin = None
        input_text = f"{password}\n"
    else:
        argv = [
            "/usr/bin/script", "-q", "/dev/null",
            "/usr/bin/sudo",
            "-p", "Approve Lid Awake with Touch ID",
            "--", "/bin/sh", "-c", command,
        ]
        stdin = subprocess.DEVNULL
        input_text = None

    try:
        proc = subprocess.run(
            argv,
            stdin=stdin,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_APPROVAL_TIMEOUT_S,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        detail = (
            "Password authentication timed out. Lid Awake was not started."
            if auth_method == "password"
            else "Touch ID approval timed out. Lid Awake was not started."
        )
        raise HTTPException(
            status_code=504,
            detail=detail,
        ) from exc
    except OSError as exc:
        detail = (
            "macOS could not start password authentication."
            if auth_method == "password"
            else "macOS could not start Touch ID approval."
        )
        raise HTTPException(
            status_code=503,
            detail=detail,
        ) from exc

    output = proc.stdout or ""
    if _SUCCESS_MARKER in output:
        return
    if auth_method == "password":
        raise HTTPException(
            status_code=409,
            detail="Password authentication failed. Check your Mac password and try again.",
        )
    raise HTTPException(
        status_code=409,
        detail=(
            "Touch ID was not approved. Confirm that sudo works with Touch ID "
            "in Terminal, then try again."
        ),
    )


@router.get("/api/power/lid-awake")
def lid_awake_status(request: Request) -> dict:
    auth.require_admin(request)
    with _LOCK:
        return _status()


@router.post("/api/power/lid-awake")
def start_lid_awake(body: LidAwakeRequest, request: Request) -> dict:
    auth.require_admin(request)
    if not _is_supported():
        raise HTTPException(status_code=501, detail="Lid Awake is available only on macOS.")
    if body.minutes not in _ALLOWED_MINUTES:  # defense in depth for direct calls
        raise HTTPException(status_code=400, detail="Choose 15, 30, or 60 minutes.")

    with _LOCK:
        was_active = _status()["active"]
        password = body.password.get_secret_value() if body.password else None
        if not was_active and body.auth_method == "password" and not password:
            raise HTTPException(status_code=400, detail="Enter your Mac password.")
        deadline = int(time.time()) + body.minutes * 60
        try:
            _write_deadline(deadline)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Could not save the Lid Awake timer.") from exc

        # Renewal only moves the deadline.  The existing root helper observes
        # it on its next one-second tick, so no second approval is necessary.
        if not was_active:
            try:
                _start_privileged_timer(
                    auth_method=body.auth_method,
                    password=password if body.auth_method == "password" else None,
                )
            except Exception:
                _clear_deadline()
                raise
        return _status()


@router.delete("/api/power/lid-awake")
def cancel_lid_awake(request: Request) -> dict:
    auth.require_admin(request)
    with _LOCK:
        _clear_deadline()
        # The privileged helper sees the missing file and restores normal
        # sleep on its next tick (at most one second from now).
        return _status()
