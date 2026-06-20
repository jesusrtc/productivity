from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"
INDEX_HTML = ROOT / "core/src/core/templates/index.html"


def _run_node(script: str) -> dict:
    if NODE is None:
        pytest.skip("node is required for frontend terminal UI tests")
    proc = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _js_between(start_marker: str, end_marker: str) -> str:
    src = LAB_APP.read_text(encoding="utf-8")
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def test_terminal_close_button_is_wired_to_persistent_close_handler() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="termKillBtn"' in html
    assert 'onclick="termKillCurrent()"' in html
    assert ">Close</button>" in html
    assert "keep it closed after reload" in html


def test_terminal_close_click_purges_saved_session_and_disables_autospawn() -> None:
    term_kill_current = _js_between(
        "async function termKillCurrent()",
        "async function termCopyAttachCmd()",
    )
    result = _run_node(
        """
const fetchCalls = [];
const disabled = [];
const confirmMessages = [];
const refreshed = [];
const refreshedByProject = [];
const statuses = [];
const attached = [];
let detached = false;
let emptyShown = false;

let termCurrentSession = 'lab-demo-claude';
let termSessions = [];
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';

function _termActiveProjectId() { return 'demo'; }
function confirm(msg) { confirmMessages.push(msg); return true; }
function termDetach() { detached = true; termCurrentSession = null; }
async function termSetAutoSpawnEnabled(projectId, enabled) {
  disabled.push({projectId, enabled});
}
async function termRefreshSessions(projectId) {
  refreshed.push(projectId);
  termSessions = [];
}
async function termRefreshSessionsByProjectId(projectId) {
  refreshedByProject.push(projectId);
  termSessions = [];
}
function termAttach(name) { attached.push(name); }
function termShowEmpty() { emptyShown = true; }
function termSetStatus(kind, text) { statuses.push({kind, text}); }
async function fetch(input, opts = {}) {
  fetchCalls.push({input: String(input), method: opts.method || 'GET'});
  return {ok: true, json: async () => ({})};
}
""" + term_kill_current + """

(async () => {
  await termKillCurrent();
  process.stdout.write(JSON.stringify({
    fetchCalls,
    disabled,
    confirmMessages,
    refreshed,
    refreshedByProject,
    statuses,
    attached,
    detached,
    emptyShown,
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["detached"] is True
    assert {
        "input": "/api/term/sessions/lab-demo-claude?purge=true",
        "method": "DELETE",
    } in result["fetchCalls"]
    assert result["disabled"] == [{"projectId": "demo", "enabled": False}]
    assert result["refreshed"] == ["demo"]
    assert result["refreshedByProject"] == []
    assert result["attached"] == []
    assert result["emptyShown"] is True
    assert result["statuses"][-1] == {
        "kind": "idle",
        "text": "no session — click + New",
    }
    assert "stay closed after reload" in result["confirmMessages"][0]


def test_project_open_does_not_autospawn_after_explicit_close() -> None:
    term_open_for_project = _js_between(
        "async function termOpenForProject(projectId)",
        "function termStartPeriodicRefresh()",
    )
    result = _run_node(
        """
const fetchCalls = [];
const autoSpawnChecks = [];
const statuses = [];
const refreshed = [];
const classes = new Set();
let detached = false;
let emptyShown = false;
let spawned = false;
let attached = [];
let termSessions = [];
const _termSessionsCache = new Map();

const document = {
  body: {
    classList: {
      add(cls) { classes.add(cls); },
      remove(cls) { classes.delete(cls); },
      contains(cls) { return classes.has(cls); },
    },
  },
};
const localStorage = { getItem() { return null; } };

function termClose() {}
function _termApplyRememberedVisibility() {}
function termRenderSessionList() {}
function _termPickRestoreName() { return null; }
function termAttach(name) { attached.push(name); }
function termDetach() { detached = true; }
function termShowEmpty() { emptyShown = true; }
function termSetStatus(kind, text) { statuses.push({kind, text}); }
function termStartPeriodicRefresh() {}
function termStartStatusPolling() {}
async function termRefreshSessions(projectId) {
  refreshed.push(projectId);
  termSessions = [];
}
async function termAutoSpawnEnabled(projectId) {
  autoSpawnChecks.push(projectId);
  return false;
}
async function termSpawnSession() { spawned = true; }
async function fetch(input, opts = {}) {
  fetchCalls.push({input: String(input), method: opts.method || 'GET'});
  if (String(input).startsWith('/api/term/sessions/saved')) {
    return {ok: true, json: async () => []};
  }
  return {ok: true, json: async () => ({})};
}
""" + term_open_for_project + """

(async () => {
  await termOpenForProject('demo');
  process.stdout.write(JSON.stringify({
    fetchCalls,
    autoSpawnChecks,
    statuses,
    refreshed,
    detached,
    emptyShown,
    spawned,
    attached,
    termOpen: classes.has('term-open'),
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["termOpen"] is True
    assert result["refreshed"] == ["demo"]
    assert result["autoSpawnChecks"] == ["demo"]
    assert result["detached"] is True
    assert result["emptyShown"] is True
    assert result["spawned"] is False
    assert result["attached"] == []
    assert result["statuses"][-1] == {
        "kind": "idle",
        "text": "no session — click + New",
    }
