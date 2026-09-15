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
        pytest.skip("node is required for frontend power control tests")
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


def _power_controls_source() -> str:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("const KEEP_ALIVE_KEY")
    end = source.index("function renderRepoTabs()", start)
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
  getElementById() { return null; },
  querySelector() { return null; },
};
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const window = {};
let currentWorkspace = null;
function renderRepoTabs() { renderCount += 1; }
""" % json.dumps(initial_storage or {}) + wake_lock_source + _power_controls_source() + """
(async () => {
""" + test_body + """
})().catch(err => {
  process.stderr.write(String(err && err.stack || err));
  process.exitCode = 1;
});
"""


def test_keep_alive_reacquires_wake_lock_when_app_becomes_visible() -> None:
    result = _run_node(_harness("""
toggleKeepAlive();
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


def test_keep_alive_works_without_entering_fullscreen() -> None:
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


def test_power_controls_are_rendered_without_focus_mode() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index("function renderRepoTabs()")
    end = source.index("function showScopedCodeSearch()", start)
    render = source[start:end]

    assert render.index("keep-alive-toggle") < render.index("lid-awake-toggle")
    assert render.index("keep-alive-toggle") < render.index("linked-terminal-sync-toggle")
    assert render.index("linked-terminal-sync-toggle") < render.index("lid-awake-toggle")
    assert "focus-toggle" not in render
    assert "focus-mode" not in LAB_SHELL_CSS.read_text(encoding="utf-8")
    assert 'role="switch"' in render
    assert 'aria-checked="${keepAliveOn}"' in render
    assert 'aria-checked="${_linkedTerminalSyncOn}"' in render
    assert "toggleLinkedTerminalSync()" in render
    assert 'data-testid="lid-awake-toggle"' in render
    assert "15, 30, 60" in _power_controls_source()


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
    source = _power_controls_source()

    assert 'type="password"' in source
    assert 'autocomplete="off"' in source
    assert "password_saved" in source
    assert "macOS Keychain" in source
    assert "LID_AWAKE_AUTH_KEY" not in source
    assert "localStorage.setItem(LID_AWAKE" not in source
    assert "localStorage.setItem('password'" not in source


def test_lid_awake_offers_working_time_overnight_and_custom_time() -> None:
    source = _power_controls_source()

    assert 'id="lidAwakeUntilTime" type="time"' in source
    assert "Past times mean tomorrow." in source
    assert "Thermal safety is always on." in source
    result = _run_node(_harness("""
const RealDate = Date;
let localNow;
globalThis.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [localNow])); }
};
globalThis.esc = globalThis.escAttr = String;
const menu = {innerHTML: '', style: {}, classList: {add() {}, remove() {}}};
const button = {setAttribute() {}, getBoundingClientRect: () => ({bottom: 20, right: 400})};
document.getElementById = id => id === 'lidAwakeMenu' ? menu : null;
document.querySelector = () => button;
currentWorkspace = {};
window.innerWidth = 800;
const choices = [];
for (const [hour, minute] of [[0, 0], [5, 59], [6, 0], [17, 59], [18, 0], [23, 59]]) {
  localNow = new RealDate(2026, 8, 15, hour, minute).getTime();
  toggleLidAwakeMenu();
  const html = menu.innerHTML;
  choices.push({
    defaultTime: /value="([0-9:]+)"/.exec(html)[1],
    overnightFirst: html.indexOf('Overnight') < html.indexOf('Working time'),
    customThird: html.indexOf('Custom time') > Math.max(html.indexOf('Overnight'), html.indexOf('Working time')),
  });
  toggleLidAwakeMenu();
}
globalThis.Date = RealDate;
process.stdout.write(JSON.stringify({choices}));
"""))

    assert result["choices"] == [
        {"defaultTime": until, "overnightFirst": overnight, "customThird": True}
        for until, overnight in [
            ("07:00", True), ("07:00", True), ("17:00", False),
            ("17:00", False), ("07:00", True), ("07:00", True),
        ]
    ]


@pytest.mark.parametrize("preset", [None, "07:00", "17:00"])
def test_lid_awake_until_posts_local_clock_time(preset: str | None) -> None:
    result = _run_node(_harness("""
let posted = null;
_lidAwakePasswordSaved = true;
window.fetch = async (_url, options) => {
  posted = JSON.parse(options.body);
  return {
    ok: true,
    json: async () => ({
      supported: true,
      active: true,
      deadline: Math.floor(Date.now() / 1000) + 3600,
      password_saved: true,
    }),
  };
};
updateLidAwakeUntilTime('09:45');
await setLidAwakeUntil(%s);
process.stdout.write(JSON.stringify(posted));
""" % (json.dumps(preset) if preset else "undefined")))

    assert result == {"until": preset or "09:45"}


def test_keep_alive_degrades_gracefully_without_browser_apis() -> None:
    result = _run_node(_harness("""
delete document.documentElement.requestFullscreen;
toggleKeepAlive();
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  stored: stored.labKeepAlive,
  wakeRequests,
  fullscreenRequests,
}));
""", wake_lock=False))

    assert result == {
        "focus": False,
        "stored": "1",
        "wakeRequests": [],
        "fullscreenRequests": 0,
    }


def test_saved_focus_mode_no_longer_changes_layout_or_keeps_display_awake() -> None:
    result = _run_node(_harness("""
await Promise.resolve();
process.stdout.write(JSON.stringify({
  focus: classes.has('focus-mode'),
  wakeRequests,
  fullscreenRequests,
  zoom: document.body.style.zoom,
}));
""", initial_storage={"labFocusMode": "1"}))

    assert result == {
        "focus": False,
        "wakeRequests": [],
        "fullscreenRequests": 0,
        "zoom": "",
    }
