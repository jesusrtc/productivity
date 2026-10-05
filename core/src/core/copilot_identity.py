"""Resolve Copilot's foreground conversation from its exact live process."""
from __future__ import annotations

from collections import OrderedDict
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
import time

import psutil

log = logging.getLogger("core.term")
READ_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 5.0
_LOCK = threading.RLock()
_LOG_CACHE: OrderedDict[Path, tuple[tuple[int, int, int], str | None]] = OrderedDict()
_TTY_CACHE: dict[Path, tuple[float, set[str], dict[str, str]]] = {}
_SESSION_ID = r"[A-Za-z0-9_-]+"
_FOREGROUND = re.compile(
    rf"^\d{{4}}-\d{{2}}-\d{{2}}T[\d:.]+Z \[INFO\] "
    rf"(Registering|Unregistering) foreground session: ({_SESSION_ID})$"
)


def _foreground(path: Path) -> str | None:
    """Bound reads, but preserve identity across continuously observed appends."""
    try:
        stat = path.stat()
        fingerprint = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        cached = _LOG_CACHE.get(path)
        if cached and cached[0] == fingerprint:
            _LOG_CACHE.move_to_end(path)
            return cached[1]
        if cached and (cached[0][0] != stat.st_ino or stat.st_size <= cached[0][1]):
            # An observed rotation or rewrite breaks the append history even
            # if the replacement is currently only a partial write.
            _LOG_CACHE.pop(path, None)
            cached = None
        start, session = max(0, stat.st_size - READ_BYTES), None
        incremental = (cached and cached[0][0] == stat.st_ino
                       and cached[0][1] < stat.st_size
                       and stat.st_size - cached[0][1] <= READ_BYTES)
        if incremental:
            start, session = cached[0][1], cached[1]
        with path.open("rb") as stream:
            stream.seek(start)
            raw = stream.read(READ_BYTES)
            after = os.fstat(stream.fileno())
        if fingerprint != (after.st_ino, after.st_size, after.st_mtime_ns):
            return None
        if raw and not raw.endswith(b"\n"):
            return None
        lines = raw.splitlines()
        if start and not incremental:
            lines = lines[1:]
        for line in lines:
            match = _FOREGROUND.fullmatch(line.decode("utf-8"))
            if match:
                session = match[2] if match[1] == "Registering" else None
        _LOG_CACHE[path] = (fingerprint, session)
        _LOG_CACHE.move_to_end(path)
        while len(_LOG_CACHE) > 256:
            _LOG_CACHE.popitem(last=False)
        return session
    except (OSError, UnicodeError) as exc:
        log.debug("Copilot foreground log unavailable: %s", exc)
        return None


def _process_session(home: Path, pid: int) -> str | None:
    try:
        process = psutil.Process(pid)
        born = process.create_time()
        candidates = []
        for path in (home / "logs").glob(f"process-*-{pid}.log"):
            match = re.fullmatch(rf"process-(\d+)-{pid}\.log", path.name)
            # Process timestamps can have sub-second precision differences.
            if match and int(match[1]) >= (born - 1) * 1000:
                candidates.append((int(match[1]), path))
        if not candidates:
            return None
        session = _foreground(max(candidates)[1])
        if not session or not process.is_running():
            return None
        # A log entry is insufficient after the conversation has been closed.
        marker = home / "session-state" / session / f"inuse.{pid}.lock"
        with marker.open("r") as stream:
            return session if stream.read(32).strip() == str(pid) else None
    except (OSError, psutil.Error) as exc:
        log.debug("Copilot process identity unavailable for PID %s: %s", pid, exc)
        return None


def sessions_by_tty(ttys: set[str]) -> dict[str, str]:
    """Never substitute a saved launch ID or a same-directory conversation."""
    wanted = {tty.removeprefix("/dev/").strip() for tty in ttys if tty}
    wanted.discard("")
    if not wanted:
        return {}
    home = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
    now = time.monotonic()
    with _LOCK:
        cached = _TTY_CACHE.get(home)
        if cached and now - cached[0] < CACHE_SECONDS and wanted.issubset(cached[1]):
            return {tty: session for tty, session in cached[2].items() if tty in wanted}
        try:
            proc = subprocess.run(
                ["ps", "-t", ",".join(sorted(wanted)), "-o", "pid=,tty=,comm="],
                capture_output=True, text=True, timeout=1.0,
            )
            if proc.returncode != 0:
                log.debug("Copilot TTY lookup failed: %s", (proc.stderr or "").strip())
                return {}
            candidates: dict[str, list[str | None]] = {}
            for line in proc.stdout.splitlines():
                fields = line.split(None, 2)
                if len(fields) != 3 or not fields[0].isdigit():
                    continue
                tty = fields[1].removeprefix("/dev/")
                if tty not in wanted or Path(fields[2]).name != "copilot":
                    continue
                candidates.setdefault(tty, []).append(_process_session(home, int(fields[0])))
            resolved = {tty: sessions[0] for tty, sessions in candidates.items()
                        if len(sessions) == 1 and sessions[0]}
            _TTY_CACHE[home] = (now, wanted, resolved)
            if len(_TTY_CACHE) > 16:
                del _TTY_CACHE[next(iter(_TTY_CACHE))]
            return dict(resolved)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("Could not resolve live Copilot conversations: %s", exc)
            return {}
