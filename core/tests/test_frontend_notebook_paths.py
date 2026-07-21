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

    assert (
        "const relPath = _workspaceRelativeNotebookPath(currentProject.path, filepath);"
        in open_block
    )
    assert "fetch(`/api/nb?path=${encodeURIComponent(relPath)}`)" in open_block
    assert "fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}`)" in open_block
    assert "bindNbCellInteractive(wrap, relPath, filepath)" in open_block
    assert "bindNbRestartKernel(container, relPath, filepath)" in open_block
    assert "const body = { path: relPath, code };" in cell_bindings
    assert "JSON.stringify({ path: relPath, cell_index: cellIndex })" in cell_bindings
    assert "JSON.stringify({ path: relPath })" in restart_binding
    assert "SELF_REPO_PATH" not in open_block
    assert "window.LAB_WORKSPACE_ROOT" in source
