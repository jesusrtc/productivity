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


def test_productivity_view_uses_workbench_without_duplicate_hidden_ids() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    lab_app = LAB_APP.read_text(encoding="utf-8")

    assert 'id="selfView"' not in html
    assert html.count('id="selfBranch"') == 1
    assert html.count('id="selfTasksList"') == 1
    assert html.count('id="selfDiffList"') == 1
    assert html.count('id="selfCommitsList"') == 1
    assert "Lab Workbench" in html
    assert "selfShowWorkbench()" in lab_app
    assert "data-workbench=\"1\"" in lab_app
    assert "selfRefreshWorkbench()" in lab_app


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
function _termIsScopeActive(projectId) { return projectId === 'demo'; }
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
function _termIsScopeActive() { return true; }
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


def test_stale_warm_project_open_does_not_attach_previous_project_terminal() -> None:
    term_open_for_project = _js_between(
        "async function termOpenForProject(projectId)",
        "function termStartPeriodicRefresh()",
    )
    result = _run_node(
        """
const attached = [];
const refreshed = [];
const rendered = [];
const classes = new Set();
let activeProject = 'beta';
let termSessions = [];
const _termSessionsCache = new Map([
  ['alpha', [{name: 'lab-alpha-claude', logical_name: 'claude', project_id: 'alpha'}]],
]);

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

function _termIsScopeActive(projectId) { return activeProject === projectId; }
function termClose() { rendered.push('close'); }
function _termApplyRememberedVisibility() { rendered.push('visibility'); }
function termRenderSessionList() { rendered.push('sessions'); }
function _termPickRestoreName() { return 'lab-alpha-claude'; }
function termAttach(name, projectId) { attached.push({name, projectId}); }
function termDetach() { rendered.push('detach'); }
function termShowEmpty() { rendered.push('empty'); }
function termSetStatus(kind, text) { rendered.push(kind + ':' + text); }
function termStartPeriodicRefresh() { rendered.push('periodic'); }
function termStartStatusPolling() { rendered.push('status'); }
async function termRefreshSessions(projectId) {
  refreshed.push(projectId);
  termSessions = [];
}
async function termAutoSpawnEnabled() { return true; }
async function termSpawnSession() { rendered.push('spawn'); }
async function fetch() {
  throw new Error('stale warm open must not fetch');
}
""" + term_open_for_project + """

(async () => {
  await termOpenForProject('alpha');
  process.stdout.write(JSON.stringify({
    attached,
    refreshed,
    rendered,
    termOpen: classes.has('term-open'),
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["attached"] == []
    assert result["refreshed"] == []
    assert result["rendered"] == []
    assert result["termOpen"] is False


def test_stale_warm_project_open_reconciles_before_attaching() -> None:
    term_open_for_project = _js_between(
        "async function termOpenForProject(projectId)",
        "function termStartPeriodicRefresh()",
    )
    result = _run_node(
        """
const attached = [];
const fetchCalls = [];
const refreshed = [];
const rendered = [];
const classes = new Set(['project-active']);
let activeProject = 'demo';
let refreshCount = 0;
let termSessions = [];
const _termSessionsCache = new Map([
  ['demo', [{name: 'lab-demo-codex-old', logical_name: 'codex', project_id: 'demo'}]],
]);

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
const location = {pathname: '/', search: '', hash: ''};

function _termIsScopeActive(projectId) { return activeProject === projectId; }
function termClose() { rendered.push('close'); }
function _termApplyRememberedVisibility() { rendered.push('visibility'); }
function termRenderSessionList() { rendered.push('sessions:' + termSessions.map(s => s.name).join(',')); }
function _termPickRestoreName() { return termSessions[0] && termSessions[0].name; }
function termAttach(name, projectId) { attached.push({name, projectId}); }
function termDetach() { rendered.push('detach'); }
function termShowEmpty() { rendered.push('empty'); }
function termSetStatus(kind, text) { rendered.push(kind + ':' + text); }
function termStartPeriodicRefresh() { rendered.push('periodic'); }
function termStartStatusPolling() { rendered.push('status'); }
async function termRefreshSessions(projectId) {
  refreshed.push(projectId);
  refreshCount += 1;
  termSessions = refreshCount >= 2
    ? [{name: 'lab-demo-codex', logical_name: 'codex', project_id: projectId}]
    : [];
}
async function termRefreshSessionsByProjectId() { throw new Error('not pseudo'); }
async function termAutoSpawnEnabled() { return true; }
async function termSpawnSession() { rendered.push('spawn'); }
async function fetch(input, opts = {}) {
  fetchCalls.push({input: String(input), method: opts.method || 'GET'});
  if (String(input).startsWith('/api/term/sessions/saved')) {
    return {ok: true, json: async () => [{name: 'codex', kind: 'claude', agent: 'codex'}]};
  }
  return {ok: true, json: async () => ({})};
}
console.info = () => {};
""" + term_open_for_project + """

(async () => {
  await termOpenForProject('demo');
  process.stdout.write(JSON.stringify({
    attached,
    fetchCalls,
    refreshed,
    rendered,
    termOpen: classes.has('term-open'),
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["termOpen"] is True
    assert result["refreshed"] == ["demo", "demo"]
    assert {
        "input": "/api/term/sessions",
        "method": "POST",
    } in result["fetchCalls"]
    assert result["attached"] == [{"name": "lab-demo-codex", "projectId": "demo"}]
    assert "periodic" in result["rendered"]
    assert "status" in result["rendered"]


def test_cached_terminal_pane_is_not_warm_after_fast_park_window() -> None:
    cache_freshness = _js_between(
        "function _termCachedPaneIsFresh(cached)",
        "  function _termIsScopeActive(projectId)",
    )
    has_open_cached_pane = _js_between(
        "function _termHasOpenCachedPane(projectId, name)",
        "  async function _termTryWarmOpen(projectId)",
    )
    result = _run_node(
        """
const WebSocket = {OPEN: 1, CLOSED: 3};
const _termCache = new Map();
const TERM_FAST_PARK_MS = 10 * 60 * 1000;
let now = 1_000_000;

Date.now = () => now;
function _termCacheKey(projectId, name) { return `${projectId}::${name}`; }
""" + cache_freshness + has_open_cached_pane + """

_termCache.set(_termCacheKey('demo', 'claude'), {
  ws: {readyState: WebSocket.OPEN},
  parkedAt: now,
});
const fresh = _termHasOpenCachedPane('demo', 'claude');

now += TERM_FAST_PARK_MS + 1;
const stale = _termHasOpenCachedPane('demo', 'claude');

_termCache.set(_termCacheKey('demo', 'closed'), {
  ws: {readyState: WebSocket.CLOSED},
  parkedAt: now,
});
const closed = _termHasOpenCachedPane('demo', 'closed');

process.stdout.write(JSON.stringify({fresh, stale, closed}));
"""
    )

    assert result == {"fresh": True, "stale": False, "closed": False}


def test_term_attach_evicts_aged_open_cached_pane() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_attach = _js_between(
        "async function termAttach(name",
        "  function termSetStatus",
    )
    result = _run_node(
        """
console.log = () => {};
console.info = () => {};
console.warn = () => {};

const WebSocket = {OPEN: 1};
const TERM_FAST_PARK_MS = 10 * 60 * 1000;
const _termCache = new Map();
const termDeadSessions = new Set();
const termReconnectAttempts = {};
let activeProject = 'demo';
let now = 1_000_000;
let evicted = [];
let ensureXtermCalls = 0;
let remembered = [];

let termSessions = [
  {name: 'lab-demo-claude', logical_name: 'claude', project_id: 'demo'},
];
let termCurrentSession = null;
let termCurrentProjectId = null;
let termWS = null;
let termXterm = null;
let termFitAddon = null;
let termContainer = null;
let termUserDetached = false;
let termReconnectTimer = null;
let termAttachRequestSeq = 0;

Date.now = () => now;
const document = {getElementById() { return null; }};
const location = {protocol: 'http:', host: 'localhost'};

function _termActiveProjectId() { return activeProject; }
function _termRecallLast() { return null; }
function _termRememberLast(projectId, logicalName) { remembered.push({projectId, logicalName}); }
async function ensureTerminalLibs() {}
function termDetach() {}
function termSetStatus() {}
function termShowRecovery() {}
function termRenderSessionList() {}
function _termClearDead() {}
function _termStripModes(s) { return s; }
function termSendResize() {}
function _termEnableWebgl() {}
function _termFocusActiveSoon() {}
function termEnsureXterm() { ensureXtermCalls += 1; termXterm = null; }
function _termMakeContainer() { throw new Error('aged cache should not reach fresh DOM creation without xterm'); }
function _termDisableWebgl() {}
function _termMarkDead() {}
function _termShowPane() {}
function _termEvictCache(name, projectId) {
  evicted.push({name, projectId});
  _termCache.delete(_termCacheKey(projectId, name));
}
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
""" + helper_block + """

_termCache.set(_termCacheKey('demo', 'lab-demo-claude'), {
  projectId: 'demo',
  name: 'lab-demo-claude',
  ws: {readyState: WebSocket.OPEN},
  xterm: {id: 'cached'},
  fitAddon: {},
  container: {},
  parkedAt: now - TERM_FAST_PARK_MS - 1,
});
""" + term_attach + """

(async () => {
  await termAttach('lab-demo-claude', 'demo');
  process.stdout.write(JSON.stringify({
    evicted,
    cacheSize: _termCache.size,
    ensureXtermCalls,
    remembered,
    termCurrentSession,
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result == {
        "evicted": [{"name": "lab-demo-claude", "projectId": "demo"}],
        "cacheSize": 0,
        "ensureXtermCalls": 1,
        "remembered": [{"projectId": "demo", "logicalName": "claude"}],
        "termCurrentSession": "lab-demo-claude",
    }


def test_project_open_aborts_after_refresh_if_user_switches_projects() -> None:
    term_open_for_project = _js_between(
        "async function termOpenForProject(projectId)",
        "function termStartPeriodicRefresh()",
    )
    result = _run_node(
        """
const attached = [];
const fetchCalls = [];
const rendered = [];
const classes = new Set(['project-active']);
let activeProject = 'alpha';
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

function _termIsScopeActive(projectId) { return activeProject === projectId; }
function termClose() { rendered.push('close'); }
function _termApplyRememberedVisibility() { rendered.push('visibility'); }
function termRenderSessionList() { rendered.push('sessions'); }
function _termPickRestoreName() { return 'lab-alpha-claude'; }
function termAttach(name, projectId) { attached.push({name, projectId}); }
function termDetach() { rendered.push('detach'); }
function termShowEmpty() { rendered.push('empty'); }
function termSetStatus(kind, text) { rendered.push(kind + ':' + text); }
function termStartPeriodicRefresh() { rendered.push('periodic'); }
function termStartStatusPolling() { rendered.push('status'); }
async function termRefreshSessions(projectId) {
  termSessions = [{name: 'lab-alpha-claude', logical_name: 'claude', project_id: projectId}];
  activeProject = 'beta';
}
async function termAutoSpawnEnabled() { rendered.push('autospawn-check'); return true; }
async function termSpawnSession() { rendered.push('spawn'); }
async function fetch(input) {
  fetchCalls.push(String(input));
  return {ok: true, json: async () => []};
}
""" + term_open_for_project + """

(async () => {
  await termOpenForProject('alpha');
  process.stdout.write(JSON.stringify({
    attached,
    fetchCalls,
    rendered,
    termOpen: classes.has('term-open'),
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["attached"] == []
    assert result["fetchCalls"] == []
    assert "autospawn-check" not in result["rendered"]
    assert result["termOpen"] is True


def test_term_attach_rejects_inactive_project_scope_before_loading_assets() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_attach = _js_between(
        "async function termAttach(name",
        "  function termSetStatus",
    )
    result = _run_node(
        """
console.log = () => {};
console.warn = () => {};

let activeProject = 'beta';
let termSessions = [
  {name: 'lab-alpha-claude', logical_name: 'claude', project_id: 'alpha'},
];
let ensureCalls = 0;
let detached = false;
let remembered = [];

let termCurrentSession = null;
let termCurrentProjectId = null;
let termWS = null;
let termXterm = null;
let termFitAddon = null;
let termContainer = null;
let termUserDetached = false;
let termReconnectTimer = null;
const _termCache = new Map();
const termDeadSessions = new Set();
const termReconnectAttempts = {};
const TERM_MAX_RECONNECT_ATTEMPTS = 3;
const TERM_RECONNECT_BASE_MS = 800;
const TERM_RECONNECT_CAP_MS = 30000;
const WebSocket = {OPEN: 1};

function _termActiveProjectId() { return activeProject; }
function _termRecallLast() { return null; }
function _termRememberLast(projectId, logicalName) { remembered.push({projectId, logicalName}); }
async function ensureTerminalLibs() { ensureCalls += 1; }
function termDetach() { detached = true; }
function termSetStatus() {}
function termShowRecovery() {}
function termRenderSessionList() {}
function _termClearDead() {}
function _termStripModes(s) { return s; }
function termSendResize() {}
function _termEnableWebgl() {}
function termEnsureXterm() {}
function _termMakeContainer() { return {classList: {add() {}}, style: {}}; }
function _termDisableWebgl() {}
function _termMarkDead() {}
function termRefreshSessions() {}
function termRefreshSessionsByProjectId() {}
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
const location = {protocol: 'http:', host: 'localhost'};
""" + helper_block + term_attach + """

(async () => {
  await termAttach('lab-alpha-claude', 'alpha');
  process.stdout.write(JSON.stringify({
    ensureCalls,
    detached,
    remembered,
    termCurrentSession,
    termCurrentProjectId,
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["ensureCalls"] == 0
    assert result["detached"] is False
    assert result["remembered"] == []
    assert result["termCurrentSession"] is None
    assert result["termCurrentProjectId"] is None


def test_soft_detach_removes_pending_pane_without_websocket() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_detach = _js_between(
        "function termDetach(soft = false)",
        "  // Compute the next reconnect delay",
    )
    result = _run_node(
        """
console.log = () => {};

let activeProject = 'demo';
let termSessions = [];
let disposed = false;
let removed = false;
const pane = {
  style: {display: 'block'},
  remove() { removed = true; },
};
const badge = {style: {display: 'inline-block'}};
const document = {
  getElementById(id) {
    if (id === 'termBody') {
      return {querySelectorAll() { return [pane]; }};
    }
    if (id === 'termAutoBadge') return badge;
    return null;
  },
};

let termCurrentSession = 'lab-demo-a';
let termCurrentProjectId = 'demo';
let termWS = null;
let termXterm = {dispose() { disposed = true; }};
let termFitAddon = {id: 'fit'};
let termContainer = pane;
let termUserDetached = false;
let termReconnectTimer = null;
let termAttachRequestSeq = 0;
const _termCache = new Map();

function _termActiveProjectId() { return activeProject; }
function _termDisableWebgl() {}
function _termEvictCache() { throw new Error('full eviction should not run for soft detach'); }
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
""" + helper_block + term_detach + """

termDetach(true);
process.stdout.write(JSON.stringify({
  disposed,
  removed,
  cacheSize: _termCache.size,
  paneDisplay: pane.style.display,
  termCurrentSession,
  termCurrentProjectId,
  termWS,
  termXterm,
  termFitAddon,
  termContainer,
  badgeDisplay: badge.style.display,
}));
"""
    )

    assert result == {
        "disposed": True,
        "removed": True,
        "cacheSize": 0,
        "paneDisplay": "none",
        "termCurrentSession": None,
        "termCurrentProjectId": None,
        "termWS": None,
        "termXterm": None,
        "termFitAddon": None,
        "termContainer": None,
        "badgeDisplay": "none",
    }


def test_same_project_attach_ignores_older_request_after_asset_load() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_attach = _js_between(
        "async function termAttach(name",
        "  function termSetStatus",
    )
    result = _run_node(
        """
console.log = () => {};
console.warn = () => {};

let activeProject = 'demo';
let termAttachRequestSeq = 0;
let termSessions = [
  {name: 'lab-demo-a', logical_name: 'a', project_id: 'demo'},
  {name: 'lab-demo-b', logical_name: 'b', project_id: 'demo'},
];
let ensureCalls = 0;
const ensureResolvers = [];
const detached = [];
const remembered = [];
const statuses = [];
let rendered = 0;

const paneA = {id: 'pane-a', style: {display: 'block'}};
const paneB = {id: 'pane-b', style: {display: 'none'}};
const badge = {style: {display: 'none'}};
const empty = {style: {display: 'block'}};
const document = {
  getElementById(id) {
    if (id === 'termBody') {
      return {querySelectorAll() { return [paneA, paneB]; }};
    }
    if (id === 'termAutoBadge') return badge;
    if (id === 'termEmpty') return empty;
    return null;
  },
};

let termCurrentSession = null;
let termCurrentProjectId = null;
let termWS = null;
let termXterm = null;
let termFitAddon = null;
let termContainer = null;
let termUserDetached = false;
let termReconnectTimer = null;
const _termCache = new Map();
const termDeadSessions = new Set();
const termReconnectAttempts = {};
const TERM_MAX_RECONNECT_ATTEMPTS = 3;
const TERM_RECONNECT_BASE_MS = 800;
const TERM_RECONNECT_CAP_MS = 30000;
const WebSocket = {OPEN: 1};

function _termActiveProjectId() { return activeProject; }
function _termRecallLast() { return null; }
function _termRememberLast(projectId, logicalName) { remembered.push({projectId, logicalName}); }
function ensureTerminalLibs() {
  ensureCalls += 1;
  return new Promise(resolve => ensureResolvers.push(resolve));
}
function termDetach(soft) {
  detached.push({soft, beforeSession: termCurrentSession, beforeProject: termCurrentProjectId});
  termCurrentSession = null;
  termCurrentProjectId = null;
  termWS = null;
  termXterm = null;
  termFitAddon = null;
  termContainer = null;
}
function termSetStatus(kind, text) { statuses.push({kind, text}); }
function termShowRecovery() {}
function termRenderSessionList() { rendered += 1; }
function _termClearDead() {}
function _termStripModes(s) { return s; }
function termSendResize() {}
function _termEnableWebgl() {}
function termEnsureXterm() {}
function _termMakeContainer() { throw new Error('cache hit should not create a fresh container'); }
function _termDisableWebgl() {}
function _termMarkDead() {}
function termRefreshSessions() {}
function termRefreshSessionsByProjectId() {}
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
const location = {protocol: 'http:', host: 'localhost'};

_termCache.set('demo::lab-demo-a', {
  projectId: 'demo',
  name: 'lab-demo-a',
  xterm: {id: 'xterm-a'},
  fitAddon: {fit() {}},
  ws: {readyState: WebSocket.OPEN},
  container: paneA,
});
_termCache.set('demo::lab-demo-b', {
  projectId: 'demo',
  name: 'lab-demo-b',
  xterm: {id: 'xterm-b'},
  fitAddon: {fit() {}},
  ws: {readyState: WebSocket.OPEN},
  container: paneB,
});
""" + helper_block + term_attach + """

(async () => {
  const first = termAttach('lab-demo-a', 'demo');
  const second = termAttach('lab-demo-b', 'demo');
  ensureResolvers[1]();
  await second;
  ensureResolvers[0]();
  await first;
  process.stdout.write(JSON.stringify({
    ensureCalls,
    detached,
    remembered,
    statuses,
    rendered,
    termCurrentSession,
    termCurrentProjectId,
    activeXterm: termXterm && termXterm.id,
    paneADisplay: paneA.style.display,
    paneBDisplay: paneB.style.display,
    cacheKeys: Array.from(_termCache.keys()).sort(),
    emptyDisplay: empty.style.display,
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["ensureCalls"] == 2
    assert result["detached"] == [
        {"soft": True, "beforeSession": None, "beforeProject": None}
    ]
    assert result["remembered"] == [{"projectId": "demo", "logicalName": "b"}]
    assert result["termCurrentSession"] == "lab-demo-b"
    assert result["termCurrentProjectId"] == "demo"
    assert result["activeXterm"] == "xterm-b"
    assert result["paneADisplay"] == "none"
    assert result["paneBDisplay"] == "block"
    assert result["cacheKeys"] == ["demo::lab-demo-a"]
    assert result["emptyDisplay"] == "none"
    assert result["statuses"][-1] == {
        "kind": "live",
        "text": "attached \u00b7 lab-demo-b",
    }
    assert result["rendered"] == 1


def test_clicking_active_terminal_cancels_pending_attach() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_attach = _js_between(
        "async function termAttach(name",
        "  function termSetStatus",
    )
    result = _run_node(
        """
console.log = () => {};
console.warn = () => {};

let activeProject = 'demo';
let termAttachRequestSeq = 0;
let termSessions = [
  {name: 'lab-demo-a', logical_name: 'a', project_id: 'demo'},
  {name: 'lab-demo-b', logical_name: 'b', project_id: 'demo'},
];
let ensureCalls = 0;
let detachCalls = 0;
let focused = 0;
const ensureResolvers = [];

function pane(id) {
  return {
    id,
    inert: false,
    style: {display: id === 'pane-b' ? 'block' : 'none'},
    attrs: {},
    contains() { return false; },
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
  };
}
const paneA = pane('pane-a');
const paneB = pane('pane-b');
const document = {
  activeElement: null,
  getElementById(id) {
    if (id === 'termBody') return {querySelectorAll() { return [paneA, paneB]; }};
    if (id === 'termEmpty') return {style: {display: 'block'}};
    if (id === 'termAutoBadge') return {style: {display: 'none'}};
    return null;
  },
};

let termCurrentSession = 'lab-demo-b';
let termCurrentProjectId = 'demo';
let termWS = {readyState: 1};
let termXterm = {focus() { focused += 1; }};
let termFitAddon = null;
let termContainer = paneB;
let termUserDetached = false;
let termReconnectTimer = null;
const _termCache = new Map();
const termDeadSessions = new Set();
const termReconnectAttempts = {};
const TERM_MAX_RECONNECT_ATTEMPTS = 3;
const TERM_RECONNECT_BASE_MS = 800;
const TERM_RECONNECT_CAP_MS = 30000;
const WebSocket = {OPEN: 1};

function _termActiveProjectId() { return activeProject; }
function _termRecallLast() { return null; }
function _termRememberLast() {}
function ensureTerminalLibs() {
  ensureCalls += 1;
  return new Promise(resolve => ensureResolvers.push(resolve));
}
function termDetach() { detachCalls += 1; }
function termSetStatus() {}
function termShowRecovery() {}
function termRenderSessionList() {}
function _termClearDead() {}
function _termStripModes(s) { return s; }
function termSendResize() {}
function _termEnableWebgl() {}
function termEnsureXterm() { throw new Error('stale attach must not create a terminal'); }
function _termMakeContainer() { throw new Error('stale attach must not create a pane'); }
function _termDisableWebgl() {}
function _termMarkDead() {}
function termRefreshSessions() {}
function termRefreshSessionsByProjectId() {}
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
const location = {protocol: 'http:', host: 'localhost'};
""" + helper_block + term_attach + """

(async () => {
  const stale = termAttach('lab-demo-a', 'demo');
  await termAttach('lab-demo-b', 'demo');
  ensureResolvers[0]();
  await stale;
  process.stdout.write(JSON.stringify({
    ensureCalls,
    detachCalls,
    termCurrentSession,
    termCurrentProjectId,
    paneADisplay: paneA.style.display,
    paneBDisplay: paneB.style.display,
    paneAHidden: paneA.attrs['aria-hidden'],
    paneBHidden: paneB.attrs['aria-hidden'],
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result == {
        "ensureCalls": 1,
        "detachCalls": 0,
        "termCurrentSession": "lab-demo-b",
        "termCurrentProjectId": "demo",
        "paneADisplay": "none",
        "paneBDisplay": "block",
        "paneAHidden": "true",
        "paneBHidden": "false",
    }


def test_hidden_parked_xterm_cannot_send_input_to_active_terminal() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    term_detach = _js_between(
        "function termDetach(soft = false)",
        "  // Compute the next reconnect delay",
    )
    term_attach = _js_between(
        "async function termAttach(name",
        "  function termSetStatus",
    )
    result = _run_node(
        """
console.log = () => {};
console.warn = () => {};

let activeProject = 'demo';
let termAttachRequestSeq = 0;
let termSessions = [
  {name: 'lab-demo-a', logical_name: 'a', project_id: 'demo'},
  {name: 'lab-demo-b', logical_name: 'b', project_id: 'demo'},
];
let xtermSeq = 0;
const panes = [];
const callbacks = {};
const focused = [];
const sockets = [];
const statuses = [];
const remembered = [];

function makePane(id) {
  return {
    id,
    inert: false,
    style: {display: 'none'},
    attrs: {},
    classList: {add() {}},
    contains(el) { return el && el.ownerPane === this; },
    setAttribute(k, v) { this.attrs[k] = v; },
    removeAttribute(k) { delete this.attrs[k]; },
    remove() { this.removed = true; },
  };
}
const badge = {style: {display: 'none'}};
const empty = {style: {display: 'block'}};
const document = {
  activeElement: null,
  getElementById(id) {
    if (id === 'termBody') return {querySelectorAll() { return panes; }};
    if (id === 'termAutoBadge') return badge;
    if (id === 'termEmpty') return empty;
    return null;
  },
};
function ResizeObserver() { this.observe = () => {}; }
function WebSocket(url) {
  this.url = url;
  this.readyState = WebSocket.OPEN;
  this.sent = [];
  this.send = (data) => this.sent.push(JSON.parse(data));
  this.close = () => { this.readyState = 3; };
  sockets.push(this);
}
WebSocket.OPEN = 1;

let termCurrentSession = null;
let termCurrentProjectId = null;
let termWS = null;
let termXterm = null;
let termFitAddon = null;
let termContainer = null;
let termUserDetached = false;
let termReconnectTimer = null;
const _termCache = new Map();
const termDeadSessions = new Set();
const termReconnectAttempts = {};
const TERM_MAX_RECONNECT_ATTEMPTS = 3;
const TERM_RECONNECT_BASE_MS = 800;
const TERM_RECONNECT_CAP_MS = 30000;

function _termActiveProjectId() { return activeProject; }
function _termRecallLast() { return null; }
function _termRememberLast(projectId, logicalName) { remembered.push({projectId, logicalName}); }
async function ensureTerminalLibs() {}
function termSetStatus(kind, text) { statuses.push({kind, text}); }
function termShowRecovery() {}
function termRenderSessionList() {}
function _termClearDead() {}
function _termStripModes(s) { return s; }
function termSendResize() {}
function _termEnableWebgl() {}
function _termDisableWebgl() {}
function _termMarkDead() {}
function termRefreshSessions() {}
function termRefreshSessionsByProjectId() {}
function _termEvictCache() { throw new Error('full eviction should not run'); }
function termEnsureXterm() {
  const id = xtermSeq === 0 ? 'xterm-a' : 'xterm-b';
  xtermSeq += 1;
  termXterm = {
    id,
    rows: 24,
    cols: 80,
    clear() {},
    dispose() {},
    open(container) { container.openedBy = id; },
    onData(cb) { callbacks[id] = cb; },
    focus() { focused.push(id); },
  };
  termFitAddon = {
    fit() {},
    proposeDimensions() { return {cols: 80, rows: 24}; },
  };
}
function _termMakeContainer() {
  const pane = makePane('pane-' + (panes.length === 0 ? 'a' : 'b'));
  panes.push(pane);
  return pane;
}
const CEREBRO_PROJECT_ID = '__cerebro__';
const SELF_PROJECT_ID = '__self__';
const LOGS_PROJECT_ID = '__logs__';
const location = {protocol: 'http:', host: 'localhost'};
""" + helper_block + term_detach + term_attach + """

(async () => {
  await termAttach('lab-demo-a', 'demo');
  await termAttach('lab-demo-b', 'demo');
  callbacks['xterm-a']('old-input');
  callbacks['xterm-b']('new-input');
  process.stdout.write(JSON.stringify({
    current: termCurrentSession,
    cacheKeys: Array.from(_termCache.keys()).sort(),
    paneA: {display: panes[0].style.display, hidden: panes[0].attrs['aria-hidden'], inert: panes[0].inert},
    paneB: {display: panes[1].style.display, hidden: panes[1].attrs['aria-hidden'], inert: panes[1].inert},
    socketASent: sockets[0].sent,
    socketBSent: sockets[1].sent,
    remembered,
  }));
})().catch((err) => {
  console.error(err && err.stack || err);
  process.exit(1);
});
"""
    )

    assert result["current"] == "lab-demo-b"
    assert result["cacheKeys"] == ["demo::lab-demo-a"]
    assert result["paneA"] == {"display": "none", "hidden": "true", "inert": True}
    assert result["paneB"] == {"display": "block", "hidden": "false", "inert": False}
    assert result["socketASent"] == []
    assert result["socketBSent"] == [{"type": "input", "data": "new-input"}]
    assert result["remembered"] == [
        {"projectId": "demo", "logicalName": "a"},
        {"projectId": "demo", "logicalName": "b"},
    ]


def test_xterm_cache_lookup_is_project_scoped() -> None:
    helper_block = _js_between(
        "function _termCacheKey(projectId, name)",
        "  // ─── Project tabs",
    )
    xterm_for = _js_between(
        "function _xtermFor(name",
        "  // Evict a session from the xterm cache",
    )
    result = _run_node(
        """
let activeProject = 'beta';
let termSessions = [];
let termCurrentProjectId = null;
let termCurrentSession = null;
let termXterm = null;
const _termCache = new Map();
const alphaXterm = {id: 'alpha-pane'};
const betaXterm = {id: 'beta-pane'};

function _termActiveProjectId() { return activeProject; }
""" + helper_block + xterm_for + """

_termCache.set(_termCacheKey('alpha', 'lab-shared-claude'), {
  projectId: 'alpha',
  name: 'lab-shared-claude',
  xterm: alphaXterm,
});
_termCache.set(_termCacheKey('beta', 'lab-shared-claude'), {
  projectId: 'beta',
  name: 'lab-shared-claude',
  xterm: betaXterm,
});

const implicit = _xtermFor('lab-shared-claude');
const alpha = _xtermFor('lab-shared-claude', 'alpha');
const beta = _xtermFor('lab-shared-claude', 'beta');

process.stdout.write(JSON.stringify({
  implicit: implicit && implicit.id,
  alpha: alpha && alpha.id,
  beta: beta && beta.id,
}));
"""
    )

    assert result == {
        "implicit": "beta-pane",
        "alpha": "alpha-pane",
        "beta": "beta-pane",
    }
