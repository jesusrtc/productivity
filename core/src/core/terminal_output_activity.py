"""Verify visible content changes before reporting tmux output as activity.

window_activity also advances for OSC titles and other invisible terminal I/O.
Use it only to gate bounded, batched captures; retain hashes, never pane text.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import subprocess
import threading
import time
import uuid

from lab import tmux_sockets


_lock = threading.Lock()
_states: dict[tuple, "_State"] = {}
_MAX_STATES = 2000
_BATCH_SIZE = 32


@dataclass
class _State:
    fingerprint: str
    raw_at: int
    geometry: tuple[int, int]
    settled: bool
    generation: str
    updated_at: float = 0
    touched: float = 0


def _fingerprint(text: str) -> str:
    # -J joins wrapped lines. Ignore padding left by clears and resizes, but
    # preserve meaningful line breaks, indentation and scrollback additions.
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).rstrip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _capture_batch(socket: str, panes: list[str], env: dict) -> dict[str, str]:
    marker = "lab-content-" + uuid.uuid4().hex
    args: list[str] = []
    for i, pane in enumerate(panes):
        if args:
            args.append(";")
        args.extend(["display-message", "-p", f"{marker}:{i}", ";",
                     "capture-pane", "-p", "-J", "-t", pane, "-S", "-200"])
    args.extend([";", "display-message", "-p", f"{marker}:{len(panes)}"])
    try:
        result = subprocess.run(tmux_sockets.command(socket, *args),
                                capture_output=True, text=True, errors="replace",
                                env=env, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    frames = re.split(rf"(?m)^{marker}:(\d+)\n", result.stdout)
    indices = [int(frames[i]) for i in range(1, len(frames), 2)]
    if indices != list(range(len(panes) + 1)):
        return {}
    return {pane: _fingerprint(frames[2 * i + 2]) for i, pane in enumerate(panes)}


def enrich(socket: str, candidates: list[tuple[dict, int, tuple[int, int]]], *, env: dict) -> None:
    """Add verified activity to rows. First observations establish a baseline.

    Concurrent scoped/global requests share the cache. An idle listing needs
    no captures; changed panes share one subprocess per batch of 32. Failures
    remain unknown rather than publishing a stale timestamp as fresh evidence.
    """
    with _lock:
        now = time.time()
        pending = []
        ready = []
        for row, raw_at, geometry in candidates:
            pane = row.get("pane_id", "")
            if not re.fullmatch(r"%\d+", pane):
                continue
            key = (socket, pane, row.get("created"), row.get("pane_pid"))
            previous = _states.get(key)
            if (previous is None or previous.raw_at != raw_at
                    or previous.geometry != geometry or not previous.settled):
                pending.append((row, raw_at, geometry, key, previous))
            else:
                previous.touched = now
                ready.append((row, previous))
        for start in range(0, len(pending), _BATCH_SIZE):
            batch = pending[start:start + _BATCH_SIZE]
            fingerprints = _capture_batch(socket, [item[0]["pane_id"] for item in batch], env)
            for row, raw_at, geometry, key, previous in batch:
                fingerprint = fingerprints.get(row["pane_id"])
                if fingerprint is None:
                    continue
                if previous is None:
                    previous = _State(fingerprint, raw_at, geometry, False, uuid.uuid4().hex)
                    _states[key] = previous
                elif fingerprint != previous.fingerprint and geometry == previous.geometry:
                    # tmux timestamps have second precision. A final capture
                    # after that second closes also catches output written
                    # immediately after the first capture in the same second.
                    previous.updated_at = max(float(raw_at), previous.updated_at + .000001)
                previous.fingerprint = fingerprint
                previous.raw_at = raw_at
                previous.geometry = geometry
                previous.settled = now >= raw_at + 1
                previous.touched = now
                ready.append((row, previous))
        for row, state in ready:
            row["output_activity"] = {
                "version": 2, "generation": state.generation,
                "updated_at": state.updated_at, "observed_at": now,
            }
        if len(_states) > _MAX_STATES:
            for key in sorted(_states, key=lambda key: _states[key].touched)[:-_MAX_STATES]:
                del _states[key]
