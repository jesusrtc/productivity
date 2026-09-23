"""On-demand host metrics, limited to processes with proven Lab ancestry.

Never select processes by a broad python/node/jupyter name or working directory.
The server and live Lab tmux panes establish ownership; their descendants are
remembered by PID AND birth time so detached children stay visible while alive.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

import psutil
from fastapi import HTTPException

from core import notebook_kernel
from lab import tmux_sockets


def _pane_roots() -> tuple[dict[int, dict], list[str]]:
    from core.routes import term

    roots, warnings = {}, []
    for generation in tmux_sockets.generations():
        try:
            result = subprocess.run(
                tmux_sockets.command(generation["name"], "list-panes", "-a", "-F",
                                     "#{pane_pid}|#{session_name}"),
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode:
                if not tmux_sockets.is_no_server_error(result.stderr):
                    warnings.append("Some terminal processes could not be inspected.")
                continue
            for line in result.stdout.splitlines():
                pid, _, name = line.partition("|")
                if pid.isdigit() and term._is_lab_tmux_name(name):
                    roots[int(pid)] = {"kind": "Terminal / server", "scope": name}
        except (OSError, subprocess.TimeoutExpired):
            warnings.append("Terminal process discovery is unavailable.")
    return roots, list(dict.fromkeys(warnings))


def _process_table() -> dict[int, dict]:
    rows = {}
    # Read only ancestry/identity for unrelated processes, never their arguments.
    for pid in psutil.pids():
        try:
            # Fresh handles avoid process_iter's cached creation times after
            # a PID is recycled between monitor samples.
            process = psutil.Process(pid)
            info = process.as_dict(attrs=["pid", "ppid", "create_time", "uids", "name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if info["create_time"] is None or info["uids"] is None:
            continue
        if info["uids"].real != os.getuid() or info["uids"].effective != os.geteuid():
            continue
        rows[process.pid] = info
    return rows


def _host_times() -> tuple[float, float]:
    times = psutil.cpu_times()._asdict()
    total = sum(v for k, v in times.items() if k not in {"guest", "guest_nice"})
    idle = times.get("idle", 0) + times.get("iowait", 0)
    return total, idle


class Monitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._known: dict[tuple[int, float], dict] = {}
        self._previous: dict[tuple[int, float], tuple[float, float]] = {}
        self._host_previous = None
        self._cached = None
        self._sampled = 0.0

    def _discover(self) -> tuple[dict[int, dict], list[str]]:
        roots, warnings = _pane_roots()
        roots[os.getpid()] = {"kind": "Lab", "scope": "Server, indexing and file scans"}
        try:
            table = _process_table()
        except (OSError, psutil.AccessDenied):
            raise HTTPException(503, "The operating system did not allow reading host processes.") from None
        # Previously verified descendants can outlive their original parent.
        self._known = {identity: source for identity, source in self._known.items()
                       if identity[0] in table and table[identity[0]]["create_time"] == identity[1]}
        selected = {pid: {**table[pid], **source} for (pid, _), source in self._known.items()}
        for pid, source in roots.items():
            if pid in table:
                selected[pid] = {**table[pid], **source}
        for pid, label in notebook_kernel.resource_processes().items():
            if pid in selected:
                selected[pid].update(kind="Jupyter", scope=label)
        children = {}
        for row in table.values():
            children.setdefault(row["ppid"], []).append(row["pid"])
        pending = list(selected)
        while pending:
            parent = pending.pop()
            # A tmux daemon can also host unrelated, non-Lab sessions. Those
            # panes are only admitted through the explicit Lab pane roots.
            if str(selected[parent].get("name", "")).lower().startswith("tmux"):
                continue
            for pid in children.get(parent, []):
                if pid in selected:
                    continue
                source = selected[parent]
                selected[pid] = {**table[pid], "kind": source["kind"], "scope": source["scope"]}
                pending.append(pid)
        # These labels refine existing ownership; stale kernel metadata cannot
        # make an unrelated, recycled PID eligible for termination.
        for pid, label in notebook_kernel.resource_processes().items():
            if pid in selected:
                selected[pid].update(kind="Jupyter", scope=label)
        self._known = {(pid, row["create_time"]): {"kind": row["kind"], "scope": row["scope"]}
                       for pid, row in selected.items()}
        return selected, warnings

    @staticmethod
    def _protected(process: psutil.Process) -> str | None:
        if process.pid in {0, 1, os.getpid()}:
            return "Lab server — includes indexing and file scan threads"
        if process.name().lower().startswith("tmux"):
            return "Shared terminal transport"
        return None

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._sampled < 2:
                return self._cached
            if now - self._sampled > 15:
                self._previous = {}
                self._host_previous = None
            selected, warnings = self._discover()
            rows, previous = [], {}
            for pid, row in selected.items():
                try:
                    process = psutil.Process(pid)
                    if process.create_time() != row["create_time"]:
                        continue
                    with process.oneshot():
                        cpu = process.cpu_times()
                        used = cpu.user + cpu.system
                        identity = (pid, row["create_time"])
                        before = self._previous.get(identity)
                        percent = None if before is None else round(max(0, used - before[1]) / max(.001, now - before[0]) * 100, 1)
                        previous[identity] = (now, used)
                        protected = self._protected(process)
                        rows.append({"pid": pid, "created": row["create_time"],
                                     "name": process.name(), "kind": row["kind"], "scope": row["scope"],
                                     "cpu_percent": percent, "memory_bytes": process.memory_info().rss,
                                     "status": process.status(), "protected": protected})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            host = _host_times()
            host_cpu = None
            if self._host_previous is not None:
                total = host[0] - self._host_previous[0]
                idle = host[1] - self._host_previous[1]
                if total > 0:
                    host_cpu = round(min(100, max(0, (total - idle) / total * 100)), 1)
            self._host_previous = host
            self._previous = previous
            memory, swap = psutil.virtual_memory(), psutil.swap_memory()
            rows.sort(key=lambda row: (row["cpu_percent"] or 0, row["memory_bytes"]), reverse=True)
            self._cached = {
                "sampled_at": time.time(), "processes": rows, "warnings": warnings,
                "host": {"cpu_percent": host_cpu, "cpu_count": psutil.cpu_count() or 1,
                         "memory_total": memory.total, "memory_used": memory.total - memory.available,
                         "memory_percent": memory.percent, "swap_used": swap.used},
            }
            self._sampled = now
            return self._cached

    def stop(self, pid: int, created: float, force: bool) -> dict:
        with self._lock:
            # Fresh ownership and identity, never trust the browser's cached list.
            selected, _ = self._discover()
            row = selected.get(pid)
            if row is None or row["create_time"] != created:
                raise HTTPException(409, "Process exited, changed, or is no longer a verified Lab process. Refresh the list.")
            try:
                process = psutil.Process(pid)
                if process.create_time() != created:
                    raise HTTPException(409, "Process changed. Refresh the list.")
                protected = self._protected(process)
                if protected:
                    raise HTTPException(403, protected)
                # psutil rechecks PID reuse before delivering either signal.
                process.kill() if force else process.terminate()
                self._cached = None
                return {"pid": pid, "signal": "SIGKILL" if force else "SIGTERM"}
            except psutil.NoSuchProcess:
                raise HTTPException(409, "Process already exited. Refresh the list.") from None
            except psutil.AccessDenied:
                raise HTTPException(403, "The operating system did not allow stopping this process.") from None
