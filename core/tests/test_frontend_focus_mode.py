from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"
LAB_SHELL_CSS = ROOT / "core/src/core/static/css/lab-shell.css"


def _run_node(script: str) -> dict:
    if NODE is None:
        pytest.skip("node is required for frontend focus mode tests")
    proc = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def _focus_mode_source() -> str:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("const FOCUS_MODE_KEY")
    end = source.index("function renderRepoTabs()", start)
    return source[start:end]


def _focus_mode_css_source() -> str:
    source = LAB_SHELL_CSS.read_text(encoding="utf-8")
    start = source.index("/* ─── Focus mode")
    end = source.index(".repo-tab.keep-alive-toggle", start)
    return source[start:end]


def _harness(
    test_body: str,
    *,
    wake_lock: bool = True,
    initial_storage: dict[str, str] | None = None,
) -> str:
    wake_lock_source = """
const navigator = {wakeLock: {request(type) {
  wakeRequests.push(type);
  const listeners = {};
  const lock = {
    released: false,
    addEventListener(type, fn) { listeners[type] = fn; },
    release() {
      if (this.released) return Promise.resolve();
      this.released = true;
      lockReleases += 1;
      if (listeners.release) listeners.release();
      return Promise.resolve();
    },
  };
  locks.push(lock);
  return Promise.resolve(lock);
}}};
""" if wake_lock else "const navigator = {};"
    return """
const classes = new Set();
const stored = %s;
const events = {};
const wakeRequests = [];
const locks = [];
let lockReleases = 0;
let fullscreenRequests = 0;
let fullscreenExits = 0;
let renderCount = 0;
const classList = {
  contains(name) { return classes.has(name); },
  add(name) { classes.add(name); },
  toggle(name, force) {
    if (force === true) classes.add(name);
    else if (force === false) classes.delete(name);
    else if (classes.has(name)) classes.delete(name);
    else classes.add(name);
    return classes.has(name);
  },
};
const document = {
  body: {classList, style: {zoom: ''}},
  visibilityState: 'visible',
  fullscreenElement: null,
  documentElement: {
    requestFullscreen() {
      fullscreenRequests += 1;
      document.fullscreenElement = this;
      return Promise.resolve();
    },
  },
  exitFullscreen() {
    fullscreenExits += 1;
    document.fullscreenElement = null;
    return Promise.resolve();
  },
  addEventListener(type, fn) { events[type] = fn; },
  querySelector() { return null; },
};
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const window = {};
let currentProject = null;
function renderRepoTabs() { renderCount += 1; }
""" % json.dumps(initial_storage or {}) + wake_lock_source + _focus_mode_source() + """
(async () => {
""" + test_body + """
})().catch(err => {
  process.stderr.write(String(err && err.stack || err));
  process.exitCode = 1;
});
"""


def test_focus_mode_enters_fullscreen_and_keeps_display_awake() -> None:
    result = _run_node(_harness("""
toggleFocusMode();
await Promise.resolve();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  stored: stored.labFocusMode,
  wakeRequests,
  fullscreenRequests,
}));
"""))

    assert result == {
        "focus": True,
        "stored": "1",
        "wakeRequests": ["screen"],
        "fullscreenRequests": 1,
    }


def test_focus_mode_keeps_home_and_project_tabs_visible() -> None:
    css = _focus_mode_css_source()

    assert "body.focus-mode .topbar" not in css
    assert "body.focus-mode .attrs-bar { display: none; }" in css
    assert "body.focus-mode .repo-tabs { top: 48px; }" in css
    assert "body.focus-mode.has-repo-tabs .diff-tabs { top: 84px; }" in css
    assert (
        "body.focus-mode.has-repo-tabs.has-diff-tabs .layout { padding-top: 124px; }"
        in css
    )


def test_exiting_browser_fullscreen_exits_focus_and_releases_wake_lock() -> None:
    result = _run_node(_harness("""
toggleFocusMode();
await Promise.resolve();
await Promise.resolve();
document.fullscreenElement = null;
events.fullscreenchange();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  stored: stored.labFocusMode,
  lockReleases,
}));
"""))

    assert result == {"focus": False, "stored": "0", "lockReleases": 1}


def test_focus_mode_reacquires_wake_lock_when_app_becomes_visible() -> None:
    result = _run_node(_harness("""
toggleFocusMode();
await Promise.resolve();
await Promise.resolve();
document.visibilityState = 'hidden';
await locks[0].release();
document.visibilityState = 'visible';
events.visibilitychange();
await Promise.resolve();
await Promise.resolve();
process.stdout.write(JSON.stringify({wakeRequests, lockReleases}));
"""))

    assert result == {"wakeRequests": ["screen", "screen"], "lockReleases": 1}


def test_keep_alive_works_without_entering_focus_or_fullscreen() -> None:
    result = _run_node(_harness("""
toggleKeepAlive();
await Promise.resolve();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  keepAlive: classes.has('keep-alive'),
  stored: stored.labKeepAlive,
  wakeRequests,
  fullscreenRequests,
}));
"""))

    assert result == {
        "focus": False,
        "keepAlive": True,
        "stored": "1",
        "wakeRequests": ["screen"],
        "fullscreenRequests": 0,
    }


def test_keep_alive_continues_after_focus_exits() -> None:
    result = _run_node(_harness("""
toggleKeepAlive();
await Promise.resolve();
await Promise.resolve();
toggleFocusMode();
await Promise.resolve();
document.fullscreenElement = null;
events.fullscreenchange();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  keepAlive: classes.has('keep-alive'),
  wakeRequests,
  lockReleases,
}));
"""))

    assert result == {
        "focus": False,
        "keepAlive": True,
        "wakeRequests": ["screen"],
        "lockReleases": 0,
    }


def test_turning_keep_alive_off_releases_its_wake_lock() -> None:
    result = _run_node(_harness("""
toggleKeepAlive();
await Promise.resolve();
await Promise.resolve();
toggleKeepAlive();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  keepAlive: classes.has('keep-alive'),
  stored: stored.labKeepAlive,
  lockReleases,
}));
"""))

    assert result == {"keepAlive": False, "stored": "0", "lockReleases": 1}


def test_keep_alive_restores_after_reload() -> None:
    result = _run_node(_harness("""
await Promise.resolve();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  keepAlive: classes.has('keep-alive'),
  wakeRequests,
  fullscreenRequests,
}));
""", initial_storage={"labKeepAlive": "1"}))

    assert result == {
        "keepAlive": True,
        "wakeRequests": ["screen"],
        "fullscreenRequests": 0,
    }


def test_keep_alive_and_lid_awake_are_rendered_beside_focus_mode() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("function renderRepoTabs()")
    end = source.index("function showScopedCodeSearch()", start)
    render = source[start:end]

    assert render.index("keep-alive-toggle") < render.index("lid-awake-toggle")
    assert render.index("lid-awake-toggle") < render.index("focus-toggle")
    assert 'role="switch"' in render
    assert 'aria-checked="${keepAliveOn}"' in render
    assert 'data-testid="lid-awake-toggle"' in render
    assert "15, 30, 60" in _focus_mode_source()


def test_lid_awake_countdown_format() -> None:
    result = _run_node(_harness("""
process.stdout.write(JSON.stringify({
  ninetySeconds: _formatLidAwakeRemaining(90000),
  oneHour: _formatLidAwakeRemaining(3600000),
  expired: _formatLidAwakeRemaining(-1000),
}));
"""))

    assert result == {
        "ninetySeconds": "1:30",
        "oneHour": "60:00",
        "expired": "0:00",
    }


def test_lid_awake_status_drives_active_label() -> None:
    result = _run_node(_harness("""
const now = Date.now;
Date.now = () => 1000000;
_applyLidAwakeStatus({supported: true, active: true, deadline: 1090});
const activeLabel = _lidAwakeLabel();
_applyLidAwakeStatus({supported: true, active: false, deadline: null});
const inactiveLabel = _lidAwakeLabel();
Date.now = now;
process.stdout.write(JSON.stringify({activeLabel, inactiveLabel}));
"""))

    assert result == {
        "activeLabel": "Lid Awake 1:30",
        "inactiveLabel": "Lid Awake",
    }


def test_lid_awake_keeps_saved_password_out_of_browser_storage() -> None:
    source = _focus_mode_source()

    assert 'type="password"' in source
    assert 'autocomplete="off"' in source
    assert "password_saved" in source
    assert "macOS Keychain" in source
    assert "LID_AWAKE_AUTH_KEY" not in source
    assert "localStorage.setItem(LID_AWAKE" not in source
    assert "localStorage.setItem('password'" not in source


def test_focus_mode_degrades_gracefully_without_browser_apis() -> None:
    result = _run_node(_harness("""
delete document.documentElement.requestFullscreen;
toggleFocusMode();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  stored: stored.labFocusMode,
  wakeRequests,
  fullscreenRequests,
}));
""", wake_lock=False))

    assert result == {
        "focus": True,
        "stored": "1",
        "wakeRequests": [],
        "fullscreenRequests": 0,
    }


def test_trackpad_pinch_zooms_only_in_focus_mode_and_resets_on_exit() -> None:
    result = _run_node(_harness("""
let preventedOutside = false;
events.wheel({ctrlKey: true, deltaY: -20, preventDefault() { preventedOutside = true; }});
const outsideZoom = document.body.style.zoom;

toggleFocusMode();
let preventedInside = false;
events.wheel({ctrlKey: true, deltaY: -20, preventDefault() { preventedInside = true; }});
const insideZoom = Number(document.body.style.zoom);

// An ordinary two-finger scroll must remain a scroll, not become zoom.
events.wheel({ctrlKey: false, deltaY: -20, preventDefault() { throw new Error('prevented scroll'); }});
const afterScrollZoom = Number(document.body.style.zoom);

applyFocusMode(false);
process.stdout.write(JSON.stringify({
  preventedOutside,
  outsideZoom,
  preventedInside,
  insideZoom,
  afterScrollZoom,
  exitedZoom: document.body.style.zoom,
}));
"""))

    assert result["preventedOutside"] is False
    assert result["outsideZoom"] == ""
    assert result["preventedInside"] is True
    assert result["insideZoom"] > 1
    assert result["afterScrollZoom"] == result["insideZoom"]
    assert result["exitedZoom"] == ""


def test_focus_trackpad_zoom_is_clamped() -> None:
    result = _run_node(_harness("""
toggleFocusMode();
events.wheel({ctrlKey: true, deltaY: -10000, preventDefault() {}});
const maxZoom = Number(document.body.style.zoom);
events.wheel({ctrlKey: true, deltaY: 10000, preventDefault() {}});
const minZoom = Number(document.body.style.zoom);
process.stdout.write(JSON.stringify({maxZoom, minZoom}));
"""))

    assert result == {"maxZoom": 3, "minZoom": 0.5}


def test_focus_trackpad_zoom_is_wired_inside_same_origin_iframes() -> None:
    result = _run_node(_harness("""
const iframeEvents = {};
const iframeDocument = {
  addEventListener(type, fn) { iframeEvents[type] = fn; },
};
_wireFocusZoomDocument(iframeDocument);
_wireFocusZoomDocument(iframeDocument);
toggleFocusMode();
let prevented = false;
iframeEvents.wheel({ctrlKey: true, deltaY: -20, preventDefault() { prevented = true; }});
process.stdout.write(JSON.stringify({
  prevented,
  zoom: Number(document.body.style.zoom),
  wired: iframeDocument.__labFocusZoomWired,
}));
"""))

    assert result["prevented"] is True
    assert result["zoom"] > 1
    assert result["wired"] is True
