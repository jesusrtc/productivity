"""Manage only pop-outs explicitly registered by a local Lab window on macOS.

The helper uses macOS Accessibility, avoiding Chrome's often stalled tab-query
Apple events. URL keys remain exact; native identity survives site redirects.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from lab import paths

_lock = threading.Lock()
_retry_after = 0.0
_failure = ""
_SOURCE = Path(__file__).with_name("native") / "ResourceWindows.swift"


def helper_app() -> Path:
    directory = paths.find_framework_root() / ".lab" / "native"
    app = directory / "Lab Resource Windows.app"
    contents = app / "Contents"
    executable = contents / "MacOS" / "LabResourceWindows"
    digest = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    stamp = directory / "resource-windows.sha256"
    if executable.is_file() and stamp.is_file() and stamp.read_text() == digest:
        return app
    executable.parent.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "com.lab.resource-windows",
        "CFBundleName": "Lab Resource Windows",
        "CFBundleExecutable": executable.name,
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "LSUIElement": True,
    }))
    subprocess.run(["/usr/bin/xcrun", "swiftc", "-module-cache-path", str(directory / "module-cache"),
                    str(_SOURCE), "-o", str(executable)], check=True, timeout=60,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True, timeout=5,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stamp.write_text(digest)
    return app


def _invoke(payload: dict) -> dict:
    app = helper_app()
    with tempfile.TemporaryDirectory(prefix="lab-resource-windows-") as directory:
        request = Path(directory) / "request.json"
        response = Path(directory) / "response.json"
        request.write_text(json.dumps(payload))
        deadline = time.monotonic() + 6
        # open -W can race a fast helper's exit and fail its initial kevent call
        # even after the response was written. Wait for our atomic result instead.
        subprocess.run(["/usr/bin/open", "-g", "-n", str(app), "--args", str(request), str(response)],
                       check=True, timeout=5, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while not response.is_file():
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('Lab Resource Windows', 6)
            time.sleep(.02)
        data = json.loads(response.read_text())
        if not isinstance(data, dict) or type(data.get("ok")) is not bool or not isinstance(data.get("group"), dict):
            raise ValueError("Invalid resource-window result")
        return data


def manage(owner: str, operation: str, **values) -> dict:
    global _retry_after, _failure
    # One bounded native operation at a time, including concurrent double clicks.
    with _lock:
        if time.monotonic() < _retry_after:
            return {"ok": False, "detail": _failure}
        state_file = paths.find_framework_root() / ".lab" / "state" / "resource-windows.json"
        try:
            state = json.loads(state_file.read_text()) if state_file.is_file() else {}
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        group = state.get(owner, {"resources": []})
        try:
            data = _invoke({"operation": operation, "group": group, **values})
        except (OSError, subprocess.SubprocessError, ValueError):
            _failure = "The macOS window helper did not respond. Try window control again from Lab."
            _retry_after = time.monotonic() + 30
            return {"ok": False, "detail": _failure}
        if data["ok"]:
            _retry_after = 0
            state.pop(owner, None)
            state[owner] = data["group"]
            # Browser window/process identities are checked on every native action.
            if len(state) > 128:
                state = dict(list(state.items())[-128:])
            state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(state))
            temporary.replace(state_file)
        resources = data.pop("group").get("resources", [])
        data["urls"] = [item["url"] for item in resources]
        return data
