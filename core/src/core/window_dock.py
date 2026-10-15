"""One explicitly registered popup per local browser's opt-in docking trial.

Private, short-lived IPC files carry geometry only. No browser URL queries,
profile changes, autostart services, or external-site content interception.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from lab import paths

_SOURCE = Path(__file__).with_name('native') / 'WindowDock.swift'
_lock = threading.Lock()
_sessions: dict[str, Path] = {}


def helper_app() -> Path:
    directory = paths.find_framework_root() / '.lab' / 'native' / 'window-dock'
    app = directory / 'Lab Window Dock.app'
    binary = app / 'Contents' / 'MacOS' / 'LabWindowDock'
    stamp = directory / 'source.sha256'
    digest = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    if binary.is_file() and stamp.is_file() and stamp.read_text() == digest:
        return app
    binary.parent.mkdir(parents=True, exist_ok=True)
    (app / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'com.lab.window-dock', 'CFBundleName': 'Lab Window Dock',
        'CFBundleExecutable': binary.name, 'CFBundlePackageType': 'APPL',
        'CFBundleVersion': '1', 'LSUIElement': True,
    }))
    subprocess.run(['/usr/bin/xcrun', 'swiftc', '-module-cache-path', str(directory / 'module-cache'),
                    str(_SOURCE), '-o', str(binary)], check=True, timeout=60, capture_output=True)
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)],
                   check=True, timeout=5, capture_output=True)
    stamp.write_text(digest)
    return app


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        if isinstance(value, dict) and type(value.get('ok')) is bool:
            return value
    except (OSError, ValueError):
        pass
    return {'ok': False, 'active': False, 'detail': 'The window helper did not return a valid status.'}


def _launch(payload: dict) -> tuple[dict, Path]:
    app = helper_app()
    directory = Path(tempfile.mkdtemp(prefix='lab-window-dock-'))
    request, response = directory / 'request.json', directory / 'response.json'
    _write(request, payload)
    try:
        subprocess.run(['/usr/bin/open', '-g', '-n', str(app), '--args', str(request), str(response),
                        str(directory / 'control.json'), str(directory / 'state.json')],
                       check=True, timeout=5, capture_output=True)
        deadline = time.monotonic() + 5
        while not response.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Window helper timed out')
            time.sleep(0.03)
        return _read(response), directory
    except Exception:
        # Even if launch succeeded but registration stalled, the helper's lease expires.
        _write(directory / 'control.json', {'operation': 'detach'})
        raise


def manage(owner: str, operation: str, **payload) -> dict:
    with _lock:
        # A controller exits after twelve seconds without a heartbeat. Prune its files.
        for key, directory in list(_sessions.items()):
            state = directory / 'state.json'
            if state.exists() and (not _read(state).get('active') or time.time() - state.stat().st_mtime > 20):
                shutil.rmtree(directory, ignore_errors=True)
                _sessions.pop(key, None)
        directory = _sessions.get(owner)
        if operation in {'update', 'detach', 'close'}:
            if not directory:
                return {'ok': operation == 'detach', 'active': False, 'detail': 'No docked popup in this view.'}
            _write(directory / 'control.json', {'operation': operation, **payload})
            if operation in {'detach', 'close'}:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and _read(directory / 'state.json').get('active'):
                    time.sleep(.03)
            return _read(directory / 'state.json')
        if operation == 'attach' and directory:
            return {'ok': False, 'active': True, 'detail': 'Detach the current popup before docking another.'}
        if operation == 'attach' and len(_sessions) >= 4:
            return {'ok': False, 'active': False, 'detail': 'Close another docking trial first.'}
        try:
            result, directory = _launch({'operation': operation, **payload})
            if operation == 'attach' and result.get('active'):
                _sessions[owner] = directory
            else:
                shutil.rmtree(directory, ignore_errors=True)
            return result
        except (OSError, subprocess.SubprocessError, ValueError, TimeoutError) as exc:
            detail = 'Could not start Lab Window Dock. Check that Xcode Command Line Tools are installed.'
            if isinstance(exc, subprocess.TimeoutExpired) or isinstance(exc, TimeoutError):
                detail = 'The window helper timed out. Your popup remains independent; try again.'
            return {'ok': False, 'active': False, 'detail': detail}
