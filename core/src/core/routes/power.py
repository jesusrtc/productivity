"""Timed macOS lid-closed wake control.

The browser Wake Lock API used by Lab's existing Keep Alive switch cannot
prevent a Mac from sleeping after its lid closes.  This route deliberately
uses macOS's system setting instead, authenticated through sudo with a password
stored by the backend in the user's encrypted macOS Keychain.

The privileged helper reads a user-owned deadline file once per second and
samples macOS thermal pressure.  That keeps renewal cheap (only the deadline
changes), survives a Lab server restart, and guarantees that the helper
restores normal sleep when the deadline expires or the Mac starts getting hot.
"""
from __future__ import annotations

import os
import select
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, SecretStr

from core import auth


router = APIRouter()

_ALLOWED_MINUTES = {15, 30, 60}
_APPROVAL_TIMEOUT_S = 120
_KEYCHAIN_TIMEOUT_S = 15
_KEYCHAIN_SERVICE = "com.neurona.lab.lid-awake"
_KEYCHAIN_LABEL = "Lab Lid Awake"
_SUCCESS_MARKER = "__LAB_LID_AWAKE_STARTED__"
_THERMAL_JXA = (
    'ObjC.import("Foundation"); '
    'Number($.NSProcessInfo.processInfo.thermalState)'
)
_THERMAL_POLL_SECONDS = 5
_THERMAL_FAIR_SAMPLES = 3
_THERMAL_PROBE_FAILURES = 3
_LOCK = threading.Lock()


class LidAwakeRequest(BaseModel):
    minutes: Literal[15, 30, 60] | None = None
    until: str | None = None
    password: SecretStr | None = None


def _deadline_path() -> Path:
    """One system-wide timer per logged-in user, shared across Lab checkouts."""
    return Path(tempfile.gettempdir()) / f"lab-lid-awake-{os.getuid()}.deadline"


def _is_supported() -> bool:
    return (
        sys.platform == "darwin"
        and Path("/usr/bin/pmset").is_file()
        and Path("/usr/bin/osascript").is_file()
        and Path("/usr/bin/security").is_file()
        and Path("/usr/bin/script").is_file()
        and Path("/usr/bin/sudo").is_file()
    )


def _keychain_account() -> str:
    return f"uid:{os.getuid()}"


def _keychain_has_password() -> bool:
    try:
        proc = subprocess.run(
            [
                "/usr/bin/security", "find-generic-password",
                "-a", _keychain_account(),
                "-s", _KEYCHAIN_SERVICE,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_KEYCHAIN_TIMEOUT_S,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _read_keychain_password() -> str | None:
    try:
        proc = subprocess.run(
            [
                "/usr/bin/security", "find-generic-password", "-w",
                "-a", _keychain_account(),
                "-s", _KEYCHAIN_SERVICE,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_KEYCHAIN_TIMEOUT_S,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    password = (proc.stdout or "").rstrip("\r\n")
    return password or None


def _save_keychain_password(password: str) -> bool:
    """Save without putting the password in argv or browser storage."""
    argv = [
        "/usr/bin/script", "-q", "/dev/null",
        "/usr/bin/security", "add-generic-password",
        "-a", _keychain_account(),
        "-s", _KEYCHAIN_SERVICE,
        "-l", _KEYCHAIN_LABEL,
        "-U",
        # macOS security(1) prompts when -w is the final argument.
        "-w",
    ]
    if not _answer_keychain_password_prompts(argv, password):
        return False
    # macOS script(1) can mask the child exit code, so verify the stored value.
    return _read_keychain_password() == password


def _answer_keychain_password_prompts(argv: list[str], password: str) -> bool:
    """Answer both security(1) prompts through its private terminal."""
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        prompts = (
            b"password data for new item:",
            b"retype password for new item:",
        )
        prompt_index = 0
        transcript = b""
        deadline = time.monotonic() + _KEYCHAIN_TIMEOUT_S
        while prompt_index < len(prompts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, _KEYCHAIN_TIMEOUT_S)
            readable, _, _ = select.select([proc.stdout], [], [], remaining)
            if not readable:
                raise subprocess.TimeoutExpired(argv, _KEYCHAIN_TIMEOUT_S)
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                return False
            transcript = (transcript + chunk)[-1024:]
            if prompts[prompt_index] not in transcript.lower():
                continue
            proc.stdin.write(password.encode("utf-8") + b"\n")
            proc.stdin.flush()
            prompt_index += 1
            transcript = b""

        proc.stdin.close()
        return proc.wait(timeout=max(0.1, deadline - time.monotonic())) == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass


def _delete_keychain_password() -> bool:
    try:
        proc = subprocess.run(
            [
                "/usr/bin/security", "delete-generic-password",
                "-a", _keychain_account(),
                "-s", _KEYCHAIN_SERVICE,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_KEYCHAIN_TIMEOUT_S,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


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
    supported = _is_supported()
    deadline = _read_deadline()
    active = bool(deadline and deadline > current)
    if deadline is not None and not active:
        _clear_deadline()
    return {
        "supported": supported,
        "active": active,
        "deadline": deadline if active else None,
        "remaining_seconds": max(0, deadline - current) if active and deadline else 0,
        "password_saved": _keychain_has_password() if supported else False,
    }


def _deadline_for_request(body: LidAwakeRequest, *, now: int | None = None) -> int:
    """Resolve either a fixed duration or the next local occurrence of HH:MM."""
    if (body.minutes is None) == (body.until is None):
        raise HTTPException(
            status_code=400,
            detail="Choose either 15, 30, or 60 minutes, or an until time.",
        )

    current = int(time.time() if now is None else now)
    if body.minutes is not None:
        return current + body.minutes * 60

    until = (body.until or "").strip()
    try:
        hour_text, minute_text = until.split(":", maxsplit=1)
        if len(hour_text) != 2 or len(minute_text) != 2:
            raise ValueError
        hour = int(hour_text)
        minute = int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Until time must use 24-hour HH:MM format, for example 17:00.",
        ) from exc

    local_now = datetime.fromtimestamp(current)
    candidate = local_now.replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )
    if candidate.timestamp() <= current:
        candidate += timedelta(days=1)
    return int(candidate.timestamp())


def _timer_watcher_loop(
    deadline_file: Path,
    *,
    thermal_probe: str | None = None,
    restore_command: str = "/usr/bin/pmset -a disablesleep 0",
    sleep_command: str = "/bin/sleep 1",
) -> str:
    """Build the detached deadline and thermal-pressure watcher."""
    path = shlex.quote(str(deadline_file))
    probe = thermal_probe or (
        "/usr/bin/osascript -l JavaScript "
        f"-e {shlex.quote(_THERMAL_JXA)} 2>/dev/null"
    )
    cleanup = f"/bin/rm -f -- {path}; {restore_command}"
    return (
        f"trap {shlex.quote(cleanup)} EXIT HUP INT TERM\n"
        f"thermal_ticks={_THERMAL_POLL_SECONDS}\n"
        "fair_samples=0\n"
        "probe_failures=0\n"
        "while :; do\n"
        f"  deadline=$(/bin/cat {path} 2>/dev/null) || break\n"
        "  case \"$deadline\" in ''|*[!0-9]*) break ;; esac\n"
        "  now=$(/bin/date +%s)\n"
        "  [ \"$deadline\" -gt \"$now\" ] || break\n"
        "  thermal_ticks=$((thermal_ticks + 1))\n"
        f"  if [ \"$thermal_ticks\" -ge {_THERMAL_POLL_SECONDS} ]; then\n"
        "    thermal_ticks=0\n"
        f"    thermal_state=$({probe})\n"
        "    case \"$thermal_state\" in\n"
        "      0) fair_samples=0; probe_failures=0 ;;\n"
        "      1)\n"
        "        probe_failures=0\n"
        "        fair_samples=$((fair_samples + 1))\n"
        f"        [ \"$fair_samples\" -lt {_THERMAL_FAIR_SAMPLES} ] || break\n"
        "        ;;\n"
        "      2|3) break ;;\n"
        "      *)\n"
        "        fair_samples=0\n"
        "        probe_failures=$((probe_failures + 1))\n"
        f"        [ \"$probe_failures\" -lt {_THERMAL_PROBE_FAILURES} ] || break\n"
        "        ;;\n"
        "    esac\n"
        "  fi\n"
        f"  {sleep_command}\n"
        "done\n"
    )


def _timer_helper_command(deadline_file: Path) -> str:
    """Return the fixed command that sudo runs as root."""
    loop = _timer_watcher_loop(deadline_file)
    # pmset runs in the foreground, then the small deadline watcher detaches.
    # A fixed marker is printed only after both steps succeed, so the caller
    # does not mistake a sudo or pmset failure for a running timer.
    return (
        "/usr/bin/pmset -a disablesleep 1; "
        "status=$?; [ \"$status\" -eq 0 ] || exit \"$status\"; "
        f"/usr/bin/nohup /bin/sh -c {shlex.quote(loop)} "
        f"</dev/null >/dev/null 2>&1 & /bin/echo {_SUCCESS_MARKER}"
    )


def _start_privileged_timer(*, password: str) -> None:
    command = _timer_helper_command(_deadline_path())
    try:
        proc = subprocess.run(
            [
                "/usr/bin/sudo", "-k", "-S", "-p", "",
                "--", "/bin/sh", "-c", command,
            ],
            input=f"{password}\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_APPROVAL_TIMEOUT_S,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail="Password authentication timed out. Lid Awake was not started.",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="macOS could not start password authentication.",
        ) from exc

    output = proc.stdout or ""
    if _SUCCESS_MARKER in output:
        return
    raise HTTPException(
        status_code=409,
        detail="Password authentication failed. Check your Mac password and try again.",
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
    if body.minutes is not None and body.minutes not in _ALLOWED_MINUTES:
        # Defense in depth for direct calls that bypass Pydantic.
        raise HTTPException(status_code=400, detail="Choose 15, 30, or 60 minutes.")

    with _LOCK:
        deadline = _deadline_for_request(body)
        current_status = _status()
        was_active = current_status["active"]
        supplied_password = body.password.get_secret_value() if body.password else None
        password = supplied_password
        used_saved_password = False
        if not was_active and not password:
            password = _read_keychain_password()
            used_saved_password = bool(password)
        if not was_active and not password:
            message = (
                "The saved password could not be read. Enter a new Mac password."
                if current_status["password_saved"]
                else "Enter your Mac password."
            )
            raise HTTPException(
                status_code=400,
                detail={"message": message, "password_saved": False},
            )
        try:
            _write_deadline(deadline)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Could not save the Lid Awake timer.") from exc

        # Renewal only moves the deadline.  The existing root helper observes
        # it on its next one-second tick, so no second approval is necessary.
        if not was_active:
            try:
                _start_privileged_timer(password=password)
            except HTTPException as exc:
                _clear_deadline()
                if exc.status_code == 409:
                    _delete_keychain_password()
                    source = "Saved Mac password" if used_saved_password else "Mac password"
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": f"{source} did not work. Enter a new password.",
                            "password_saved": False,
                        },
                    ) from exc
                raise
            except Exception:
                _clear_deadline()
                raise

            if supplied_password and not _save_keychain_password(supplied_password):
                status = _status()
                status["warning"] = (
                    "Lid Awake started, but macOS Keychain could not save the password."
                )
                return status
        return _status()


@router.delete("/api/power/lid-awake/password")
def forget_lid_awake_password(request: Request) -> dict:
    auth.require_admin(request)
    with _LOCK:
        _delete_keychain_password()
        if _keychain_has_password():
            raise HTTPException(
                status_code=503,
                detail="macOS Keychain could not forget the saved password.",
            )
        return {"password_saved": False}


@router.delete("/api/power/lid-awake")
def cancel_lid_awake(request: Request) -> dict:
    auth.require_admin(request)
    with _LOCK:
        _clear_deadline()
        # The privileged helper sees the missing file and restores normal
        # sleep on its next tick (at most one second from now).
        return _status()
