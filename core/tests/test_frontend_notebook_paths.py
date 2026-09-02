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
        pytest.skip("node is required for frontend notebook path tests")
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


def _js_between(start_marker: str, end_marker: str) -> str:
    src = LAB_APP.read_text(encoding="utf-8")
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def test_notebook_path_uses_active_workspace_when_framework_root_differs() -> None:
    helpers = _js_between(
        "function _normalizeAbsolutePath(path)",
        "function renderNotebookCell(cell, status, index = null)",
    )
    result = _run_node(
        """
const WORKSPACE_ROOT = '/Users/jcortes/src/workspaces/main';
"""
        + helpers
        + """
const relative = _workspaceRelativeNotebookPath(
  '/Users/jcortes/src/workspaces/main/projects/investigations',
  'investigations/2026-W29/onCall/analysis.ipynb',
);
const failures = [];
for (const [project, file] of [
  ['/Users/jcortes/CEREBRO/projects/investigations', 'analysis.ipynb'],
  ['/Users/jcortes/src/workspaces/main-other/projects/investigations', 'analysis.ipynb'],
  ['/Users/jcortes/src/workspaces/main/projects/investigations', '../escape.ipynb'],
  ['/Users/jcortes/src/workspaces/main/projects/investigations', '/absolute.ipynb'],
]) {
  try {
    _workspaceRelativeNotebookPath(project, file);
    failures.push(null);
  } catch (err) {
    failures.push(err.message);
  }
}
process.stdout.write(JSON.stringify({relative, failures}));
"""
    )

    assert result["relative"] == (
        "projects/investigations/investigations/2026-W29/onCall/analysis.ipynb"
    )
    assert not result["relative"].startswith("/")
    assert all(result["failures"])


def test_notebook_path_can_follow_a_project_in_another_workspace() -> None:
    helpers = _js_between(
        "function _normalizeAbsolutePath(path)",
        "function renderNotebookCell(cell, status, index = null)",
    )
    result = _run_node(
        """
const WORKSPACE_ROOT = '/Volumes/SSD/workspaces/productivity';
"""
        + helpers
        + """
const relative = _workspaceRelativeNotebookPath(
  '/Users/jcortes/workspaces/local/projects/test',
  'agent-demo.ipynb',
  '/Users/jcortes/workspaces/local',
);
process.stdout.write(JSON.stringify({relative}));
"""
    )

    assert result["relative"] == "projects/test/agent-demo.ipynb"


def test_notebook_deep_link_resolves_project_under_active_workspace() -> None:
    helpers = _js_between(
        "function _normalizeAbsolutePath(path)",
        "function renderNotebookCell(cell, status, index = null)",
    )
    deep_link = _js_between(
        "let _nbHashProject = null;",
        "const _effectiveProject = urlProject || _nbHashProject;",
    )
    result = _run_node(
        """
const WORKSPACE_ROOT = '/Users/jcortes/src/workspaces/main';
const location = {
  hash: '#/nb?path=projects/investigations/notebooks/analysis.ipynb',
  href: 'http://lab.test/#/nb?path=projects/investigations/notebooks/analysis.ipynb',
};
const historyCalls = [];
const lastDocs = [];
const history = {replaceState(_state, _title, url) { historyCalls.push(String(url)); }};
function setLastProjectDoc(project, doc) { lastDocs.push({project, doc}); }
const urlProject = null;
"""
        + helpers
        + deep_link
        + """
process.stdout.write(JSON.stringify({_nbHashProject, historyCalls, lastDocs}));
"""
    )

    expected_project = "/Users/jcortes/src/workspaces/main/projects/investigations"
    assert result["_nbHashProject"] == expected_project
    assert result["lastDocs"] == [
        {"project": expected_project, "doc": "notebooks/analysis.ipynb"}
    ]
    assert (
        "project=%2FUsers%2Fjcortes%2Fsrc%2Fworkspaces%2Fmain%2Fprojects%2Finvestigations"
        in result["historyCalls"][0]
    )


def test_notebook_deep_link_keeps_an_explicit_cross_workspace_project() -> None:
    helpers = _js_between(
        "function _normalizeAbsolutePath(path)",
        "function renderNotebookCell(cell, status, index = null)",
    )
    deep_link = _js_between(
        "let _nbHashProject = null;",
        "const _effectiveProject = urlProject || _nbHashProject;",
    )
    result = _run_node(
        """
const WORKSPACE_ROOT = '/Volumes/SSD/workspaces/productivity';
const location = {
  hash: '#/nb?path=projects/test/agent-demo.ipynb',
  href: 'http://lab.test/?project=%2FUsers%2Fjcortes%2Fworkspaces%2Flocal%2Fprojects%2Ftest#/nb?path=projects/test/agent-demo.ipynb',
};
const historyCalls = [];
const lastDocs = [];
const history = {replaceState(_state, _title, url) { historyCalls.push(String(url)); }};
function setLastProjectDoc(project, doc) { lastDocs.push({project, doc}); }
const urlProject = '/Users/jcortes/workspaces/local/projects/test';
"""
        + helpers
        + deep_link
        + """
process.stdout.write(JSON.stringify({_nbHashProject, historyCalls, lastDocs}));
"""
    )

    expected_project = "/Users/jcortes/workspaces/local/projects/test"
    assert result["_nbHashProject"] == expected_project
    assert result["lastDocs"] == [
        {"project": expected_project, "doc": "agent-demo.ipynb"}
    ]
    assert "project=%2FUsers%2Fjcortes%2Fworkspaces%2Flocal%2Fprojects%2Ftest" in (
        result["historyCalls"][0]
    )


def test_cold_project_hydration_does_not_stomp_a_remembered_notebook() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    select_repo = _js_between(
        "async function selectRepo(projectKey)",
        "async function loadDiff()",
    )

    assert "const remembered = getLastProjectDoc(currentProject.path);" in select_repo
    assert "showProjectInfo({keepShell: true});" in select_repo
    assert "if (remembered) openProjectDoc(remembered);" in select_repo
    assert "showProjectInfo({keepShell: !remembered});" not in source


def test_builtin_jupyter_tab_needs_no_server_proxy_configuration() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    helpers = _js_between(
        "function _projectNotebookEntries(files)",
        "async function _loadProjectNotebookEntries(projectPath)",
    )
    result = _run_node(
        helpers
        + """
const entries = _projectNotebookEntries([
  {path: 'README.md', type: 'file', mtime: 30},
  {path: 'notebooks/older.ipynb', type: 'file', mtime: 10},
  {path: 'notebooks', type: 'dir', mtime: 50},
  {path: 'research/newer.IPYNB', type: 'file', mtime: 20},
]);
process.stdout.write(JSON.stringify(entries.map(entry => entry.path)));
"""
    )

    assert result == ["research/newer.IPYNB", "notebooks/older.ipynb"]
    assert 'onclick="openProjectNotebooks()"' in source
    assert "Lab Jupyter notebooks — no server configuration required" in source
    assert "Notebooks are scoped to this project" in source
    assert "A notebook created in another project appears in that project's Jupyter tab" in source
    assert "Create the first notebook here" in source
    assert 'onclick="openProjectNotebooks({showLauncher:true})"' in source
    assert "☷ All notebooks" in source
    assert ".nb-notebook-list, .nb-runtime-open, .nb-interrupt-kernel" in css
    assert ".nb-notebook-list:hover" in css
    assert "window.openProjectNotebooks = openProjectNotebooks" in source
    assert "__proxy__/Jupyter" not in source


def test_large_notebooks_restore_last_read_cell_and_offer_jump_controls() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    helpers = _js_between(
        "function _notebookPositionKey(scope, path)",
        "function _notebookCommittedCells(container)",
    )
    result = _run_node(
        """
const values = new Map();
const localStorage = {
  getItem(key) { return values.has(key) ? values.get(key) : null; },
  setItem(key, value) { values.set(key, String(value)); },
};
"""
        + helpers
        + """
const attrs = new Map([['data-cell-id', 'stable-cell'], ['data-cell-index', '41']]);
const cell = {getAttribute(name) { return attrs.get(name) || null; }};
_writeNotebookPosition('workspace-a', 'projects/demo/large.ipynb', cell);
_setNotebookCodeHidden('workspace-a', 'projects/demo/large.ipynb', true);
const saved = _readNotebookPosition('workspace-a', 'projects/demo/large.ipynb');
const other = _readNotebookPosition('workspace-b', 'projects/demo/large.ipynb');
const codeHidden = _isNotebookCodeHidden('workspace-a', 'projects/demo/large.ipynb');
const otherCodeHidden = _isNotebookCodeHidden('workspace-b', 'projects/demo/large.ipynb');
process.stdout.write(JSON.stringify({saved, other, codeHidden, otherCodeHidden}));
"""
    )

    assert result == {
        "saved": {"cellId": "stable-cell", "index": 41},
        "other": None,
        "codeHidden": True,
        "otherCodeHidden": False,
    }
    peek_helper = _js_between(
        "function _setNotebookCodePeek(notebook, target)",
        "function _notebookCommittedCells(container)",
    )
    peek_result = _run_node(
        peek_helper
        + """
function fakeCell(id) {
  const classes = new Set();
  function fakeButton() {
    const attrs = new Map([['aria-expanded', 'false']]);
    return {
      textContent: 'Show code', title: '',
      setAttribute(name, value) { attrs.set(name, String(value)); },
      getAttribute(name) { return attrs.get(name) || null; },
    };
  }
  const headerButton = fakeButton();
  const outputButton = fakeButton();
  return {
    id, headerButton, outputButton,
    classList: {
      contains(name) { return classes.has(name); },
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
    },
    querySelectorAll(selector) {
      return selector === '[data-nb-peek-code]' ? [headerButton, outputButton] : [];
    },
  };
}
const first = fakeCell('first');
const second = fakeCell('second');
const notebook = {
  querySelectorAll(selector) {
    if (selector === '.nb-cell.nb-code-peek') {
      return [first, second].filter(cell => cell.classList.contains('nb-code-peek'));
    }
    if (selector === '[data-nb-peek-code]') {
      return [first.headerButton, first.outputButton, second.headerButton, second.outputButton];
    }
    return [];
  },
};
const firstOpen = _setNotebookCodePeek(notebook, first);
const afterFirst = {
  open: firstOpen && firstOpen.id,
  first: first.classList.contains('nb-code-peek'),
  second: second.classList.contains('nb-code-peek'),
  headerLabel: first.headerButton.textContent,
  outputLabel: first.outputButton.textContent,
  expanded: first.outputButton.getAttribute('aria-expanded'),
};
const secondOpen = _setNotebookCodePeek(notebook, second);
const afterSecond = {
  open: secondOpen && secondOpen.id,
  first: first.classList.contains('nb-code-peek'),
  second: second.classList.contains('nb-code-peek'),
  firstLabel: first.headerButton.textContent,
  secondHeaderLabel: second.headerButton.textContent,
  secondOutputLabel: second.outputButton.textContent,
};
const closed = _setNotebookCodePeek(notebook, second);
process.stdout.write(JSON.stringify({
  afterFirst,
  afterSecond,
  closed: closed && closed.id,
  anyOpen: first.classList.contains('nb-code-peek') || second.classList.contains('nb-code-peek'),
  secondExpanded: second.outputButton.getAttribute('aria-expanded'),
}));
"""
    )
    assert peek_result == {
        "afterFirst": {
            "open": "first", "first": True, "second": False,
            "headerLabel": "Hide code", "outputLabel": "Hide code",
            "expanded": "true",
        },
        "afterSecond": {
            "open": "second", "first": False, "second": True,
            "firstLabel": "Show code", "secondHeaderLabel": "Hide code",
            "secondOutputLabel": "Hide code",
        },
        "closed": None,
        "anyOpen": False,
        "secondExpanded": "false",
    }
    position_helpers = _js_between(
        "function _notebookCommittedCells(container)",
        "function _renderNbJumpControls(cellCount, codeHidden = false, actionsHtml = '')",
    )
    position_result = _run_node(
        "const window = {innerHeight: 900};\n"
        + position_helpers
        + """
function fakeCell(id, index, top, queuePos = null) {
  return {
    getAttribute(name) {
      if (name === 'data-cell-id') return id;
      if (name === 'data-cell-index') return String(index);
      if (name === 'data-queue-pos') return queuePos == null ? null : String(queuePos);
      return null;
    },
    getBoundingClientRect() { return {top}; },
  };
}
const cells = [fakeCell('a', 0, -120), fakeCell('b', 2, 160), fakeCell('c', 3, 260)];
const stable = _resolveNotebookPosition(cells, {cellId: 'b', index: 1});
const clamped = _resolveNotebookPosition(cells, {cellId: 'deleted', index: 99});
const reading = _notebookReadingCell(cells);
const running = _notebookRunningCell({
  querySelectorAll() {
    return [fakeCell('queued', 4, 0, 2), fakeCell('active', 5, 0, 1)];
  },
});
process.stdout.write(JSON.stringify({
  stable: stable.getAttribute('data-cell-id'),
  clamped: clamped.getAttribute('data-cell-id'),
  reading: reading.getAttribute('data-cell-id'),
  running: running.getAttribute('data-cell-id'),
}));
"""
    )
    assert position_result == {
        "stable": "b", "clamped": "c", "reading": "b", "running": "active",
    }
    assert 'data-nb-jump="start"' in source
    assert 'data-nb-jump="end"' in source
    assert "data-nb-jump-running" in source
    assert "data-nb-toggle-code" in source
    assert "data-nb-peek-code" in source
    assert "nb-code-peek-header-actions" in source
    assert "_setNotebookCodePeek(notebook, cell)" in source
    assert "_setNotebookCodeHidden(scope, path, codeHidden)" in source
    assert 'data-cell-type="code"' in source
    assert "_bindNbNavigation(" in source
    assert "notebookWorkspace.workspaceId || notebookWorkspace.workspaceRoot" in source
    assert "running || _resolveNotebookPosition" not in source
    assert "jump(_notebookRunningCell(notebook), 'start')" in source
    assert '<span aria-hidden="true">&lt;/&gt;</span>' in source
    assert 'class="nb-jump-word"' not in source
    assert ".nb-jump-controls" in css
    assert "position:fixed" in css
    assert "top:var(--nb-jump-top, 88px)" in css
    assert "left:max(var(--sidebar-width), 150px); right:0" in css
    assert "width:auto; max-width:none" in css
    assert "border-radius:0" in css
    assert "box-shadow:none" in css
    assert "body.sidebar-collapsed .nb-jump-controls { left:0; }" in css
    assert "right:var(--term-width)" in css
    assert "right:24px" not in css
    assert ".nb-jump-controls-spacer" in css
    assert "bottom:22px" not in css
    assert ".nb-container.nb-code-hidden" in css
    assert ".nb-jump-controls .nb-jump-running" in css
    assert ".nb-container.nb-code-hidden .nb-cell-del { display:none; }" in css
    assert ":not(.nb-code-peek) > .nb-cell-edit-wrap" in css
    assert ".nb-output-code-toggle { display:inline-flex; }" in css
    assert ".nb-cell-no-outputs" in css
    assert "scroll-margin-top: calc(var(--nb-jump-top, 88px) + 100px)" in css


def test_hidden_notebook_code_keeps_pins_plus_one_transient_slot() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    helpers = _js_between(
        "function _notebookPinnedCodeKey(scope, path)",
        "function _notebookCommittedCells(container)",
    )
    result = _run_node(
        """
const values = new Map();
const localStorage = {
  getItem(key) { return values.has(key) ? values.get(key) : null; },
  setItem(key, value) { values.set(key, String(value)); },
  removeItem(key) { values.delete(key); },
};
"""
        + helpers
        + """
function fakeButton(kind) {
  const attrs = new Map();
  return {
    kind, textContent: kind === 'pin' ? 'Pin code' : 'Show code', title: '',
    setAttribute(name, value) { attrs.set(name, String(value)); },
    getAttribute(name) { return attrs.get(name) || null; },
  };
}
function fakeCell(id) {
  const classes = new Set();
  const pin = fakeButton('pin');
  const peek = fakeButton('peek');
  return {
    id, pin, peek,
    getAttribute(name) {
      if (name === 'data-cell-id') return id;
      if (name === 'data-cell-index') return id.slice(-1);
      return null;
    },
    classList: {
      contains(name) { return classes.has(name); },
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      toggle(name, force) {
        if (force === undefined ? !classes.has(name) : force) classes.add(name);
        else classes.delete(name);
      },
    },
    querySelectorAll(selector) {
      if (selector === '[data-nb-pin-code]') return [pin];
      if (selector === '[data-nb-peek-code]') return [peek];
      return [];
    },
  };
}
const first = fakeCell('cell-1');
const second = fakeCell('cell-2');
const third = fakeCell('cell-3');
const fourth = fakeCell('cell-4');
const cells = [first, second, third, fourth];
const notebook = {
  querySelectorAll(selector) {
    if (selector === '.nb-cell[data-cell-type="code"]') return cells;
    if (selector === '.nb-cell.nb-code-peek') {
      return cells.filter(cell => cell.classList.contains('nb-code-peek'));
    }
    if (selector === '[data-nb-peek-code]') return cells.map(cell => cell.peek);
    return [];
  },
};
const scope = 'workspace-a';
const path = 'projects/demo/large.ipynb';
_setNotebookCodePinned(scope, path, first, true);
_setNotebookCodePinned(scope, path, second, true);
_applyNotebookCodePins(notebook, scope, path);
_setNotebookCodePeek(notebook, third);
const afterThird = {
  third: third.classList.contains('nb-code-peek'),
  fourth: fourth.classList.contains('nb-code-peek'),
};
_setNotebookCodePeek(notebook, fourth);
process.stdout.write(JSON.stringify({
  saved: _readNotebookPinnedCode(scope, path),
  otherScope: _readNotebookPinnedCode('workspace-b', path),
  pinned: [first, second, third, fourth].map(cell => cell.classList.contains('nb-code-pinned')),
  afterThird,
  afterFourth: {
    third: third.classList.contains('nb-code-peek'),
    fourth: fourth.classList.contains('nb-code-peek'),
    label: fourth.peek.textContent,
  },
  pinLabels: [first.pin.textContent, second.pin.textContent, third.pin.textContent],
}));
"""
    )

    assert result == {
        "saved": ["id:cell-1", "id:cell-2"],
        "otherScope": [],
        "pinned": [True, True, False, False],
        "afterThird": {"third": True, "fourth": False},
        "afterFourth": {"third": False, "fourth": True, "label": "Hide code"},
        "pinLabels": ["Unpin code", "Unpin code", "Pin code"],
    }
    assert "data-nb-pin-code" in source
    assert "_applyNotebookCodePins(notebook, scope, path)" in source
    assert "!cell.classList.contains('nb-code-pinned')" in source
    assert ":not(.nb-cell-running):not(.nb-code-pinned):not(.nb-code-peek)" in css
    assert ".nb-cell.nb-code-pinned [data-nb-peek-code]" in css
    assert ".nb-cell:is(.nb-code-pinned, .nb-code-peek) > .nb-outputs" in css


def test_all_notebook_operations_reuse_workspace_relative_path() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    open_block = _js_between(
        "// Notebooks: render cells via /api/nb",
        "// All other files: fetch content + comments",
    )
    cell_bindings = _js_between(
        "function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved, workspaceId = null)",
        "function renderNbAddCellButton()",
    )
    restart_binding = _js_between(
        "async function _requestNbKernelRestart(relPath, workspaceId = null)",
        "function bindNbAddCellButton(container, relPath, filepath, workspaceId = null)",
    )

    assert "const notebookWorkspace = _notebookWorkspaceContext(currentProject);" in open_block
    assert "currentProject.path, filepath, notebookWorkspace.workspaceRoot" in open_block
    assert "fetch(`/api/nb?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`)" in open_block
    assert "fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`)" in open_block
    assert "fetch(`/api/nb/runtime?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`)" in open_block
    assert "wrap, relPath, filepath, null, notebookWorkspace.workspaceId" in open_block
    assert "bindNbRestartKernel(container, relPath, filepath, notebookWorkspace.workspaceId)" in open_block
    assert "bindNbRuntimePanel(container, relPath, filepath, notebookWorkspace.workspaceId)" in open_block
    assert "bindNbInterruptKernel(container, relPath, notebookWorkspace.workspaceId)" in open_block
    assert "const body = { path: relPath, code, actor: 'human' };" in cell_bindings
    assert "if (workspaceId) body.workspace = workspaceId;" in cell_bindings
    assert "if (cellId) body.cell_id = cellId;" in cell_bindings
    assert "...(workspaceId ? {workspace: workspaceId} : {})" in cell_bindings
    assert "...(workspaceId ? {workspace: workspaceId} : {})" in restart_binding
    assert "/api/notebook?repo=${encodeURIComponent(docRoot)}" in open_block
    assert "read-only notebook" in open_block
    assert "Move or copy into a workspace project to execute" in open_block
    assert "SELF_REPO_PATH" not in open_block
    assert "window.LAB_WORKSPACE_ROOT" in source


def test_project_runtime_panel_exposes_python_libraries_and_cli_configuration() -> None:
    render = _js_between(
        "function _nbRuntimeLines(values)",
        "function bindNbRuntimePanel(container, relPath, filepath, workspaceId = null)",
    )
    result = _run_node(
        """
function esc(value) { return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;'); }
"""
        + render
        + """
const html = renderNbRuntimePanel({status: 'ready', spec: {
  version: 1, mode: 'local', kind: 'existing', python: '/client/.venv/bin/python',
  packages: ['pandas==2.3.2'], editable: ['libs/sdk'], imports: ['client_sdk'],
  cli_paths: ['tools/bin'], cli_checks: [{command: 'client-cli', args: ['--version']}],
  environment: {PROFILE: 'test'}, working_dir: '.', validation_code: 'assert True',
}, active: {python: '/client/.venv/bin/python'}}, 'projects/acme/notebooks/x.ipynb');
process.stdout.write(JSON.stringify({html}));
"""
    )
    html = result["html"]
    for expected in (
        "Project Runtime",
        "Shared by people and agents",
        "Local Jupyter",
        "/client/.venv/bin/python",
        "pandas==2.3.2",
        "libs/sdk",
        "tools/bin",
        "client-cli",
        "Build &amp; validate in Jupyter",
    ):
        assert expected in html


def test_project_runtime_panel_saves_builds_and_interrupts_through_shared_api() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    runtime_binding = _js_between(
        "function bindNbRuntimePanel(container, relPath, filepath, workspaceId = null)",
        "function bindNbInterruptKernel(container, relPath, workspaceId = null)",
    )
    interrupt_binding = _js_between(
        "function bindNbInterruptKernel(container, relPath, workspaceId = null)",
        "async function bindNbRestartKernel(container, relPath, filepath, workspaceId = null)",
    )
    assert "fetch('/api/nb/runtime'" in runtime_binding
    assert "fetch('/api/nb/runtime/build'" in runtime_binding
    assert "packages: lines('packages')" in runtime_binding
    assert "cli_paths: lines('cli_paths')" in runtime_binding
    assert "cli_checks: cliChecks" in runtime_binding
    assert "fetch('/api/nb/session/interrupt'" in interrupt_binding
    assert "Cmd/Ctrl+Enter" in source


def test_notebook_run_all_sequences_cells_and_can_restart_first() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    binding = _js_between(
        "async function _requestNbKernelRestart(relPath, workspaceId = null)",
        "async function bindNbRestartKernel(container, relPath, filepath, workspaceId = null)",
    )
    result = _run_node(
        """
const calls = [];
const alerts = [];
const opened = [];
const removedDrafts = [];
const listeners = {};
const currentProject = {workspace_id: 'workspace-a'};
function _projectWorkspaceId(project) { return project.workspace_id; }
function _currentOpenNotebookRelPath() { return 'projects/demo/notebooks/x.ipynb'; }
function _cellDraftKey(path, cell) { return `draft:${path}:${cell}`; }
const localStorage = {removeItem(key) { removedDrafts.push(key); }};
function confirm() { return true; }
function alert(message) { alerts.push(String(message)); }
async function openProjectDoc(path, options) { opened.push({path, options}); }
function response(data) {
  return {ok: true, status: 200, async json() { return data; }};
}
async function fetch(url, options) {
  const body = JSON.parse(options.body);
  calls.push({url, body});
  return response(url.endsWith('/restart') ? {restarted: true} : {cell: {outputs: []}});
}
function button(name) {
  return {
    name, disabled: false, textContent: '', innerHTML: '', title: '', attrs: {},
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(event, fn) { listeners[`${name}:${event}`] = fn; },
  };
}
const run = button('run');
const restart = button('restart');
function cell(id, index, code) {
  return {
    getAttribute(name) {
      if (name === 'data-cell-id') return id;
      if (name === 'data-cell-index') return String(index);
      return null;
    },
    querySelector(selector) {
      return selector === '.nb-cell-edit-area' ? {value: code} : null;
    },
  };
}
const cells = [cell('first', 0, 'a = 1'), cell('second', 2, 'print(a)')];
const container = {
  querySelector(selector) {
    if (selector === '.nb-run-all') return run;
    if (selector === '.nb-restart-run-all') return restart;
    return null;
  },
  querySelectorAll(selector) {
    return selector.includes('data-cell-type') ? cells : [];
  },
};
"""
        + binding
        + """
bindNbRunAll(
  container,
  'projects/demo/notebooks/x.ipynb',
  'notebooks/x.ipynb',
  'workspace-a',
);
Promise.resolve(listeners['restart:click']()).then(() => {
  process.stdout.write(JSON.stringify({calls, alerts, opened, removedDrafts}));
});
"""
    )

    assert [call["url"] for call in result["calls"]] == [
        "/api/nb/session/restart",
        "/api/nb/exec",
        "/api/nb/exec",
    ]
    assert [call["body"].get("cell_id") for call in result["calls"][1:]] == [
        "first",
        "second",
    ]
    assert all(call["body"]["workspace"] == "workspace-a" for call in result["calls"])
    assert result["alerts"] == []
    assert result["opened"] == [
        {"path": "notebooks/x.ipynb", "options": {"preserveScroll": True}}
    ]
    assert result["removedDrafts"] == [
        "draft:projects/demo/notebooks/x.ipynb:first",
        "draft:projects/demo/notebooks/x.ipynb:second",
    ]
    assert "toolbarActionsHtml" in source
    assert "${runtimeBadge}${runAllButtonsHtml}${interruptBtnHtml}${restartBtnHtml}" in source
    assert "${notebookListBtnHtml}${sessionBadge}" in source
    assert ".nb-run-all" in css
    assert ".nb-restart-run-all" in css


def test_notebook_cells_show_actor_action_and_live_elapsed_time() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    elapsed_helpers = _js_between(
        "function _formatNbElapsed(milliseconds)",
        "function renderNbCellInteractive(cell, index, relPath, opts)",
    )
    result = _run_node(
        elapsed_helpers
        + """
process.stdout.write(JSON.stringify({
  short: _formatNbElapsed(1250),
  minute: _formatNbElapsed(65000),
  hour: _formatNbElapsed(3661000),
}));
"""
    )
    assert result == {"short": "1.3s", "minute": "1m 5s", "hour": "1h 1m 1s"}
    assert "nb-cell-actor-${actor}" in source
    assert "${actor}${action ? ` · ${action}` : ''}" in source
    assert "data-nb-started-at-ms" in source
    assert "finished in ${_formatNbElapsed(durationMs)}" in source
    assert "actor: 'human'" in source


def test_agent_api_running_snapshot_renders_visible_running_cell() -> None:
    renderer = _js_between(
        "function _formatNbElapsed(milliseconds)",
        "function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved, workspaceId = null)",
    )
    result = _run_node(
        """
function esc(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;');
}
function _highlightCellSource(value) { return esc(value); }
function _renderNbOutput(output) {
  return `<div class="nb-output">${esc(output.content || '')}</div>`;
}
function _renderNbPeekCodeButton() {
  return '<button data-nb-peek-code>Show code</button>';
}
function _renderNbPinCodeButton() {
  return '<button data-nb-pin-code>Pin code</button>';
}
function _isOutputCollapsed() { return false; }
function _isCellSeen() { return true; }
"""
        + renderer
        + """
const startedAt = (Date.now() - 2100) / 1000;
const html = renderNbCellInteractive({
  id: 'agent-cell',
  cell_type: 'code',
  execution_count: 7,
  metadata: {
    lab_pending: true,
    lab_actor: 'agent',
    lab_action: 'created',
    lab_started_at: startedAt,
  },
  source: "print('first')\\n",
  outputs: [{type: 'text', content: 'first\\n'}],
}, 3, 'projects/demo/notebooks/live.ipynb', {queuePos: 1, liveSequence: 2});
process.stdout.write(JSON.stringify({html}));
"""
    )

    html = result["html"]
    assert "nb-cell-running" in html
    assert "nb-cell-agent" in html
    assert "agent · created" in html
    assert "running · 2.1s" in html
    assert 'data-nb-started-at-ms="' in html
    assert '<span class="nb-exec">[1]</span>' in html
    assert 'readonly aria-busy="true"' in html
    assert 'data-queue-pos="1"' in html
    assert html.count(" disabled") == 2
    assert "data-nb-peek-code" in html
    assert "first\n" in html


def test_starting_a_cell_clears_stale_output_without_stealing_scroll() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    bindings = _js_between(
        "function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved, workspaceId = null)",
        "function renderNbAddCellButton()",
    )
    open_block = _js_between(
        "// Notebooks: render cells via /api/nb",
        "// All other files: fetch content + comments",
    )

    assert 'data-local-running-output="true"' in bindings
    assert "Starting execution… first output will stream here." in bindings
    assert "existing.hidden = true;" in bindings
    assert "localRunOutputSnapshot.existing.hidden = false;" in bindings
    assert "ta.readOnly = on;" in bindings
    assert "gutter.textContent = '[*]';" in bindings
    assert "_nbNavigationRefreshRunning()" in bindings
    assert "focusTarget.scrollIntoView" not in bindings
    assert "wrap.scrollIntoView({ block: 'center'" not in bindings
    assert "runningCell.querySelector('.nb-cell-header') || runningCell" not in open_block
    assert "const runningCell = container.querySelector" not in open_block
    assert "runningCell.scrollIntoView({ behavior: 'smooth', block: 'center' })" not in open_block
    assert "delBtn.classList.contains('nb-cell-del-confirming')" in bindings
    assert "Click again within 3s to delete this cell" in bindings
    assert ".nb-output-local-running" in css
    assert "@keyframes nb-running-spin" in css


def test_notebook_live_execution_replays_and_applies_ordered_ws_deltas() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    open_block = _js_between(
        "// Notebooks: render cells via /api/nb",
        "// All other files: fetch content + comments",
    )
    live_block = _js_between(
        "// Live notebook execution events share the global authenticated WebSocket",
        "// Terminal panel",
    ) if source.index("// Terminal panel") > source.index(
        "// Live notebook execution events share the global authenticated WebSocket"
    ) else source[source.index(
        "// Live notebook execution events share the global authenticated WebSocket"
    ):]

    assert "`/api/nb/live?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`" in open_block
    assert "liveByCell" in open_block
    assert "live.sequence" in open_block
    assert "latestNbRes" in open_block
    assert "realCells.splice(at, 0" in open_block
    assert "event.type === 'notebook-execution'" in live_block
    assert "incomingSequence > currentSequence + 1" in live_block
    assert "event.operation === 'replace'" in live_block
    assert "body.insertAdjacentHTML('beforeend', rendered)" in live_block
    assert "_reconcileOpenNotebook(relPath, workspaceId)" in live_block
    assert "_reconcileOpenNotebook(reconnectNotebook, reconnectWorkspaceId)" in live_block
    assert "const workspaceId = String(event.workspace || '');" in live_block
    assert "const liveKey = _nbLiveKey(workspaceId, relPath);" in live_block
    assert "const idxAttr = clientPending ? 'new' : String(index);" in source
    assert "if (draftKey && !isServerRunning)" in source
