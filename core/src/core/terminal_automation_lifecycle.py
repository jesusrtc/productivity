"""Explicit recovery of workspace automations; reads never replay a launch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

from lab import storage

from core import terminal_automations

NAME = re.compile(r"^automation-[0-9a-f]{32}-[1-9]\d*$")
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "nu"}


def read(folder: Path) -> dict:
    path = folder / ".lab" / "terminal-automation-runs.json"
    if not path.is_file():
        return {}
    raw = path.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Automation launch history is too large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid automation launch history")
    return {name: row for name, row in data.items()
            if NAME.fullmatch(name) and isinstance(row, dict)
            and all(isinstance(row.get(key), str) and row[key] for key in ("command", "shell", "cwd", "launch_id", "label"))}


def save(folder: Path, rows: dict) -> None:
    path = folder / ".lab" / "terminal-automation-runs.json"
    storage.write_json(path, rows)
    os.chmod(path, 0o600)


def remember(folder: Path, session: dict, command: str, shell: str,
             health_command: str = "", guidelines: list[dict] | None = None,
             request_id: str | None = None) -> dict:
    with terminal_automations.lock:
        rows = read(folder)
        row = {"command": command, "shell": shell, "cwd": session["cwd"],
               "label": session.get("label") or session["logical_name"],
               "name": session["name"], "tmux_socket": session["tmux_socket"],
               "launch_id": uuid.uuid4().hex, "updated_at": time.time(),
               "health_command": health_command, "guidelines": guidelines or [], "request_id": request_id}
        rows[session["logical_name"]] = row
        save(folder, rows)
        return row


def adopt_legacy(folder: Path, meta: dict, workspace_id: str) -> dict:
    """Recover only our exact old wrapper, never infer a command from a label."""
    with terminal_automations.lock:
        rows = read(folder)
        changed = False
        for session in meta.values():
            logical = session.get("logical_name", "")
            if session.get("workspace_id") != workspace_id or not NAME.fullmatch(logical) or logical in rows:
                continue
            try:
                argv = shlex.split(session.get("cmd", ""))
                if len(argv) != 3 or argv[:2] != ["/bin/sh", "-c"]:
                    continue
                lexer = shlex.shlex(argv[2], posix=True, punctuation_chars=True)
                lexer.whitespace_split = True
                parts = list(lexer)
                if parts[1:3] != ["-l", "-c"] or len(parts) < 5 or parts[4] != ";":
                    continue
                program = parts[3]
                first, command = program.split("\n", 1)
                cwd = Path(session["cwd"])
                if first != f"cd {shlex.quote(str(cwd))} || exit":
                    continue
                if argv != terminal_automations.shell_command(parts[0], cwd, command):
                    continue
                rows[logical] = {"command": command, "shell": parts[0], "cwd": str(cwd),
                                 "name": session.get("name", ""),
                                 "label": session.get("label") or logical,
                                 "tmux_socket": session.get("tmux_socket", "default"),
                                 "launch_id": uuid.uuid4().hex, "updated_at": 0,
                                 "health_command": ""}
                changed = True
            except (ValueError, KeyError, IndexError, TypeError):
                continue
        if changed:
            save(folder, rows)
        return rows


def processes(live: list[dict]) -> dict[int, dict] | None:
    """One bounded process read, limited to the requested automation TTYs."""
    ttys = sorted({str(row.get("pane_tty", "")).removeprefix("/dev/") for row in live})
    ttys = [tty for tty in ttys if re.fullmatch(r"(?:tty[\w]+|pts/\d+)", tty)]
    if not ttys:
        return None
    try:
        proc = subprocess.run(["ps", "-t", ",".join(ttys), "-o", "pid=,ppid=,stat=,comm="],
                              capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1) or proc.stderr.strip():
        return None
    rows = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit():
            rows[int(parts[0])] = {"ppid": int(parts[1]), "stat": parts[2], "comm": parts[3]}
    return rows


def connection_kind(command: str) -> str:
    if re.search(r"(?:^|[\s;|&])(?:[^\s;|&]*/)?tmux\s", command):
        return "tmux"
    if re.search(r"(?:^|[\s;|&])(?:[^\s;|&]*/)?ssh\s", command):
        return "ssh"
    return "process"


def status(run: dict, live: dict | None, listing_known: bool,
           snapshot: dict[int, dict] | None) -> dict:
    kind = connection_kind(run["command"])
    result = {"state": "unknown", "kind": kind, "can_relaunch": False, "can_restart": False,
              "launch_id": run["launch_id"], "reason": "Status unavailable"}
    if not listing_known:
        return result
    if live and (live.get("windows", 1) != 1 or live.get("pane_count", 1) != 1):
        return {**result, "reason": "Terminal has multiple panes or windows"}
    # Explicit merged-tab renewal can rerun an owned running command. Keep
    # the launch cooldown and single-pane ownership guard for that action too.
    result["can_restart"] = time.time() - run.get("updated_at", 0) >= 2
    stopped = live is None or live.get("pane_dead") is True
    if live and not stopped:
        if snapshot is None:
            return result
        pid = live.get("pane_pid", 0)
        root = snapshot.get(pid)
        if root is None:
            return result
        descendants = {pid}
        while True:
            children = {child for child, row in snapshot.items()
                        if row["ppid"] in descendants and not row["stat"].startswith("Z")}
            if children <= descendants:
                break
            descendants |= children
        name = Path(root["comm"]).name.lstrip("-")
        shells = SHELLS | {Path(run["shell"]).name}
        stopped = len(descendants) == 1 and (name in shells or root["stat"].startswith("Z"))
        if not stopped:
            return {**result, "state": "running", "reason": "Running"}
    # A shell may be observed just before the new program forks. Never offer
    # recovery during that initial window or after a concurrently accepted click.
    if time.time() - run.get("updated_at", 0) < 2:
        return {**result, "state": "starting", "reason": "Starting"}
    if run.get("health_command"):
        try:
            check = subprocess.run([run["shell"], "-l", "-c", run["health_command"]],
                                   cwd=run["cwd"], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            return result
        if check.returncode == 0:
            return {**result, "state": "running", "reason": "Background service running"}
        if check.returncode != 1:
            return result
    reason = "Terminal session ended" if live is None else {
        "ssh": "SSH disconnected", "tmux": "tmux client disconnected", "process": "Process exited",
    }[kind]
    return {**result, "state": "stopped", "can_relaunch": True, "reason": reason}
