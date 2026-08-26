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
        pytest.skip("node is required for frontend sidebar config tests")
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


def test_pinned_files_remain_in_the_normal_project_tree() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    sidebar = _between(
        "async function _refreshProjectSidebar",
        "function paintProjectShell()",
    )

    assert "const otherFiles = fileEntries;" in sidebar
    assert "fileEntries.filter(f => !pinnedSet.has(f.name))" not in sidebar
    assert "buildSidebarTree([...dirEntries, ...mainFiles])" in sidebar


def test_recent_files_respect_freshness_extensions_and_sort_order() -> None:
    helpers = _between(
        "let showDotFiles = false;",
        "function filterDotFiles(nodes)",
    )
    result = _run_node(
        """
const stored = {};
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const document = {addEventListener() {}};
"""
        + helpers
        + """
_sidebarFileConfig = {
  showHidden: false,
  showRecent: true,
  recentMinutes: 60,
  trackMode: 'extensions',
  extensions: ['md'],
};
const files = [
  {path: 'docs/older.md', type: 'file', mtime: 9700},
  {path: 'docs/newer.md', type: 'file', mtime: 9950},
  {path: 'script.py', type: 'file', mtime: 9990},
  {path: 'docs/stale.md', type: 'file', mtime: 6000},
  {path: 'docs', type: 'dir', mtime: 9999},
];
const recent = _sidebarRecentFiles(files, 10000).map(file => file.path);
process.stdout.write(JSON.stringify({
  recent,
  markdown: _sidebarFileExtension('README.md'),
  extensionless: _sidebarFileExtension('Makefile'),
}));
"""
    )

    assert result == {
        "recent": ["docs/newer.md", "docs/older.md"],
        "markdown": "md",
        "extensionless": "__none__",
    }


def test_recent_tree_compacts_single_child_paths_but_preserves_branches() -> None:
    tree_helpers = _between(
        "function buildSidebarTree(entries)",
        "// ─── Explorer secondary-click menu",
    )
    sidebar_helpers = _between(
        "let showDotFiles = false;",
        "function filterDotFiles(nodes)",
    )
    result = _run_node(
        """
const stored = {};
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const document = {addEventListener() {}};
const currentProject = {path: '/workspace/project'};
const esc = value => String(value);
const escAttr = value => String(value);
const symlinkClass = () => '';
const symlinkTitle = () => '';
const symlinkMarker = () => '';
const fileIconHtml = () => '<i></i>';
const _treeIsOpen = () => true;
"""
        + tree_helpers
        + sidebar_helpers
        + """
const now = Date.now() / 1000;
const recentFiles = [
  {path: 'core/src/core/routes/diff.py', type: 'file', mtime: now},
  {path: 'core/src/core/static/js/lab-app.js', type: 'file', mtime: now},
  {path: 'core/tests/test_project_routes.py', type: 'file', mtime: now},
];
const branched = _sidebarRecentTreeModel(recentFiles);
const core = branched.folders[0];
const source = core.children.folders.find(folder => folder.label === 'src/core');
const isolated = _sidebarRecentTreeModel([
  {path: 'alpha/beta/gamma/file.md', type: 'file'},
]);
_sidebarFileConfig = {
  showHidden: false,
  showRecent: true,
  recentMinutes: 60,
  trackMode: 'all',
  extensions: [],
};
const html = _sidebarRecentSectionHtml(recentFiles, null);
process.stdout.write(JSON.stringify({
  root: branched.folders.map(folder => folder.label),
  coreChildren: core.children.folders.map(folder => folder.label),
  sourceChildren: source.children.folders.map(folder => folder.label),
  isolated: isolated.folders.map(folder => folder.label),
  rendered: [
    html.includes('>core/</div>'),
    html.includes('>src/core/</div>'),
    html.includes('>tests/</div>'),
    !html.includes('sidebar-shortcut-path'),
  ],
}));
"""
    )

    assert result == {
        "root": ["core"],
        "coreChildren": ["src/core", "tests"],
        "sourceChildren": ["routes", "static/js"],
        "isolated": ["alpha/beta/gamma"],
        "rendered": [True, True, True, True],
    }


def test_sidebar_config_modal_and_all_sidebar_surfaces_are_wired() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    template = INDEX.read_text(encoding="utf-8")

    for element_id in (
        "sidebarFileConfigModal",
        "sidebarConfigHidden",
        "sidebarConfigRecent",
        "sidebarConfigFreshness",
        "sidebarConfigExtensions",
    ):
        assert f'id="{element_id}"' in template

    # Repository, project, framework, and workspace sidebar renderers all use
    # the same settings entry point instead of four divergent checkboxes.
    assert source.count("_sidebarFileConfigButtonHtml()") >= 4
    assert "Show hidden files</label>" not in source
    assert source.count("_sidebarRecentSectionHtml(") >= 4
