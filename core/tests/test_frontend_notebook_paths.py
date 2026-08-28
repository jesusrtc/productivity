from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"


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


def test_builtin_jupyter_tab_needs_no_server_proxy_configuration() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
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
    assert "Built into Lab. Every .ipynb keeps its own kernel" in source
    assert "window.openProjectNotebooks = openProjectNotebooks" in source
    assert "__proxy__/Jupyter" not in source


def test_all_notebook_operations_reuse_workspace_relative_path() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    open_block = _js_between(
        "// Notebooks: render cells via /api/nb",
        "// All other files: fetch content + comments",
    )
    cell_bindings = _js_between(
        "function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved)",
        "function renderNbAddCellButton()",
    )
    restart_binding = _js_between(
        "async function bindNbRestartKernel(container, relPath, filepath)",
        "function bindNbAddCellButton(container, relPath, filepath)",
    )

    assert "_workspaceRelativeNotebookPathOrNull(currentProject.path, filepath)" in open_block
    assert "fetch(`/api/nb?path=${encodeURIComponent(relPath)}`)" in open_block
    assert "fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}`)" in open_block
    assert "fetch(`/api/nb/runtime?path=${encodeURIComponent(relPath)}`)" in open_block
    assert "bindNbCellInteractive(wrap, relPath, filepath)" in open_block
    assert "bindNbRestartKernel(container, relPath, filepath)" in open_block
    assert "bindNbRuntimePanel(container, relPath, filepath)" in open_block
    assert "bindNbInterruptKernel(container, relPath)" in open_block
    assert "const body = { path: relPath, code, actor: 'human' };" in cell_bindings
    assert "if (cellId) body.cell_id = cellId;" in cell_bindings
    assert "{ path: relPath, cell_id: cellId }" in cell_bindings
    assert "JSON.stringify({ path: relPath })" in restart_binding
    assert "/api/notebook?repo=${encodeURIComponent(docRoot)}" in open_block
    assert "read-only notebook" in open_block
    assert "Move or copy into a workspace project to execute" in open_block
    assert "SELF_REPO_PATH" not in open_block
    assert "window.LAB_WORKSPACE_ROOT" in source


def test_project_runtime_panel_exposes_python_libraries_and_cli_configuration() -> None:
    render = _js_between(
        "function _nbRuntimeLines(values)",
        "function bindNbRuntimePanel(container, relPath, filepath)",
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
        "function bindNbRuntimePanel(container, relPath, filepath)",
        "function bindNbInterruptKernel(container, relPath)",
    )
    interrupt_binding = _js_between(
        "function bindNbInterruptKernel(container, relPath)",
        "async function bindNbRestartKernel(container, relPath, filepath)",
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
