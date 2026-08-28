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
        "function renderNotebookCell(cell, status)",
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
        "function renderNotebookCell(cell, status)",
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
        "function renderNotebookCell(cell, status)",
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
        "function renderNotebookCell(cell, status)",
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
        "async function bindNbRestartKernel(container, relPath, filepath, workspaceId = null)",
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
    assert html.count(" disabled") == 2
    assert "first\n" in html


def test_starting_a_cell_clears_stale_output_and_focuses_its_code() -> None:
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
    assert "wrap.querySelector('.nb-cell-header') || wrap" in bindings
    assert "scrollIntoView({ block: 'start', behavior: 'smooth' })" in bindings
    assert "wrap.scrollIntoView({ block: 'center'" not in bindings
    assert "runningCell.querySelector('.nb-cell-header') || runningCell" in open_block
    assert "scrollIntoView({ behavior: 'smooth', block: 'start' })" in open_block
    assert "runningCell.scrollIntoView({ behavior: 'smooth', block: 'center' })" not in open_block
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
