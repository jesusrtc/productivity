from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[2]
LAB_APP = ROOT / "core/src/core/static/js/lab-app.js"
INDEX = ROOT / "core/src/core/templates/index.html"


def _run_node(script: str) -> dict:
    if NODE is None:
        pytest.skip("node is required for frontend explorer tests")
    proc = subprocess.run(
        [NODE, "-e", script], cwd=ROOT, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"node failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def _between(start_marker: str, end_marker: str) -> str:
    source = LAB_APP.read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_explorer_context_menu_is_wired_to_all_real_tree_surfaces() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    template = INDEX.read_text(encoding="utf-8")

    # Repository tree + per-project tree + shared self/workspace tree.
    assert source.count('data-entry-kind="folder"') >= 3
    assert source.count('data-entry-kind="file"') >= 5
    assert "document.addEventListener('contextmenu'" in source
    assert "View Git history" in source
    assert "New file here" in source
    assert "New folder here" in source
    assert "Rename" in source
    assert "Delete ${ctx.kind}" in source

    for element_id in (
        "explorerContextMenu",
        "explorerEntryModal",
        "explorerDeleteModal",
        "explorerHistoryModal",
    ):
        assert f'id="{element_id}"' in template


def test_explorer_folder_and_active_path_helpers() -> None:
    helpers = _between(
        "function _explorerParentForCreate(ctx)",
        "async function _explorerMenuAction(action)",
    ) + _between(
        "function _explorerPathAffected(activePath, targetPath, kind)",
        "function _explorerClearDocCache(root, path, kind)",
    )
    result = _run_node(helpers + """
const values = {
  folderParent: _explorerParentForCreate({kind: 'folder', path: 'docs/design'}),
  fileParent: _explorerParentForCreate({kind: 'file', path: 'docs/design/spec.md'}),
  rootFileParent: _explorerParentForCreate({kind: 'file', path: 'README.md'}),
  childAffected: _explorerPathAffected('docs/design/spec.md', 'docs/design', 'folder'),
  siblingUnaffected: _explorerPathAffected('docs/design-2/spec.md', 'docs/design', 'folder'),
  renamedChild: _explorerRenamedActivePath(
    'docs/design/spec.md', 'docs/design', 'docs/product-design', 'folder'
  ),
};
process.stdout.write(JSON.stringify(values));
""")

    assert result == {
        "folderParent": "docs/design",
        "fileParent": "docs/design",
        "rootFileParent": "",
        "childAffected": True,
        "siblingUnaffected": False,
        "renamedChild": "docs/product-design/spec.md",
    }


def test_saved_diff_files_use_structured_diff_renderer_everywhere() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    assert "function renderStoredDiffDocument(filepath, data, container)" in source
    assert "mode === 'split' ? renderSplit(file) : renderUnified(file)" in source

    repo_open = _between(
        "async function openProjectFile(filepath)",
        "function renderProjectFileView(filepath, fileContent)",
    )
    project_open = _between(
        "async function _renderDocInto(filepath, container",
        "async function openProjectDoc(filepath",
    )
    assert "/api/project-diff-file" in repo_open
    assert "renderStoredDiffDocument(filepath, data, content)" in repo_open
    assert "/api/project-diff-file" in project_open
    assert "renderStoredDiffDocument(filepath, data, container)" in project_open
    assert "lower.endsWith('.diff')" in source
    assert "lower.endsWith('.patch')" in source
