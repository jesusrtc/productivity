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
const stored = {
  'labSidebarFileConfig-v1': JSON.stringify({recentMinutes: 10080}),
};
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const document = {addEventListener() {}};
const window = {};
"""
        + helpers
        + """
const loadedRecentMinutes = _sidebarFileConfig.recentMinutes;
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
  loadedRecentMinutes,
  markdown: _sidebarFileExtension('README.md'),
  extensionless: _sidebarFileExtension('Makefile'),
}));
"""
    )

    assert result == {
        "recent": ["docs/newer.md", "docs/older.md"],
        "loadedRecentMinutes": 4320,
        "markdown": "md",
        "extensionless": "__none__",
    }


def test_worktree_picker_scopes_file_sections_and_keeps_per_worktree_colors() -> None:
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
const currentRepo = null;
const currentProject = {path: '/repo', repos: [{path: '/repo/nested'}]};
const SELF_REPO_PATH = '/framework';
const document = {
  body: {classList: {contains() { return false; }}},
  addEventListener() {},
};
const window = {};
const esc = value => String(value);
const escAttr = value => String(value);
"""
        + helpers
        + """
_sidebarWorktreeFolders = [
  {name: 'feature-a', path: '/worktrees/feature-a'},
  {name: 'feature-b', path: '/worktrees/feature-b'},
];
_sidebarFileConfig = {
  showHidden: false,
  showRecent: true,
  recentMinutes: 60,
  trackMode: 'all',
  extensions: [],
  worktreeFolder: '/worktrees',
  worktreeColors: {'/worktrees/feature-b': '#123abc'},
  selectedWorktrees: {'/repo': '/worktrees/feature-b'},
};
const picker = _sidebarWorktreePickerHtml('/repo');
const scope = _sidebarWorktreeScopeStartHtml('/repo');
const scopedRoot = _sidebarScopedRoot('/repo');
let historyRequest = null;
function openRepositoryHistory(request) { historyRequest = request; }
sidebarOpenRepositoryHistory({getAttribute() { return '/repo'; }});
const selectedHistoryRoot = historyRequest && historyRequest.root;
delete _sidebarFileConfig.selectedWorktrees['/repo'];
sidebarOpenRepositoryHistory({getAttribute() { return '/repo'; }});
const mainHistoryRoot = historyRequest && historyRequest.root;
_sidebarFileConfig.worktreeFolder = '';
const mainPicker = _sidebarWorktreePickerHtml('/repo');
process.stdout.write(JSON.stringify({
  scopedRoot,
  pickerHasRoot: picker.includes('<option value="">main</option>'),
  pickerHasSelected: picker.includes('value="/worktrees/feature-b" selected'),
  pickerColor: picker.includes('value="#123abc"'),
  pickerHasHistory: picker.includes('sidebarOpenRepositoryHistory(this)'),
  pickerHasGithub: picker.includes('<svg viewBox="0 0 16 16"'),
  mainHasHistory: mainPicker.includes('sidebarOpenRepositoryHistory(this)'),
  mainHasLabel: mainPicker.includes('sidebar-worktree-current') && mainPicker.includes('>main</span>'),
  scopeColor: scope.includes('--sidebar-worktree-color:#123abc'),
  scopePath: scope.includes('data-worktree-path="/worktrees/feature-b"'),
  selectedHistoryRoot,
  mainHistoryRoot,
  defaultColor: _sidebarWorktreeColor('/worktrees/feature-a'),
}));
"""
    )

    assert result == {
        "scopedRoot": "/worktrees/feature-b",
        "pickerHasRoot": True,
        "pickerHasSelected": True,
        "pickerColor": True,
        "pickerHasHistory": True,
        "pickerHasGithub": True,
        "mainHasHistory": True,
        "mainHasLabel": True,
        "scopeColor": True,
        "scopePath": True,
        "selectedHistoryRoot": "/worktrees/feature-b",
        "mainHistoryRoot": "/repo/nested",
        "defaultColor": "#6e7681",
    }


def test_worktree_discovery_cache_is_scoped_to_repository_root() -> None:
    helpers = _between(
        "let showDotFiles = false;",
        "function filterDotFiles(nodes)",
    )
    result = _run_node(
        """
const stored = {};
const urls = [];
const localStorage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const currentRepo = null;
const currentProject = {path: '/project-a', repos: [{path: '/repos/repo-a'}]};
const SELF_REPO_PATH = '/framework';
const document = {
  body: {classList: {contains() { return false; }}},
  addEventListener() {},
};
const window = {};
const fetch = async url => {
  urls.push(url);
  const repo = new URL(`http://lab${url}`).searchParams.get('repo');
  const name = repo.split('/').pop();
  return {
    ok: true,
    async json() {
      return {
        path: '/worktrees',
        folders: [{name, path: `/worktrees/${name}`}],
      };
    },
  };
};
"""
        + helpers
        + """
(async () => {
  const first = await _sidebarDiscoverWorktrees('/worktrees');
  await _sidebarDiscoverWorktrees('/worktrees');
  currentProject.path = '/project-b';
  currentProject.repos = [{path: '/repos/repo-b'}];
  const second = await _sidebarDiscoverWorktrees('/worktrees');
  process.stdout.write(JSON.stringify({
    callCount: urls.length,
    urls,
    first: first.map(row => row.name),
    second: second.map(row => row.name),
  }));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exitCode = 1;
});
"""
    )

    assert result == {
        "callCount": 2,
        "urls": [
            "/api/sidebar-worktrees?path=%2Fworktrees&repo=%2Frepos%2Frepo-a",
            "/api/sidebar-worktrees?path=%2Fworktrees&repo=%2Frepos%2Frepo-b",
        ],
        "first": ["repo-a"],
        "second": ["repo-b"],
    }


def test_recent_diagnostic_reports_each_readme_mtime_and_filter_result() -> None:
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
const events = [];
const document = {addEventListener() {}};
const window = {labLog: {
  info(message, details) { events.push({level: 'info', message, details}); },
  warning(message, details) { events.push({level: 'warning', message, details}); },
  flush() { events.push({level: 'flush'}); },
}};
"""
        + helpers
        + """
_sidebarFileConfig = {
  showHidden: false,
  showRecent: true,
  recentMinutes: 60,
  trackMode: 'all',
  extensions: [],
};
const files = [
  {path: 'repositories/queries/README.md', type: 'file', mtime: 9950},
  {path: 'docs/README.md', type: 'file', mtime: 6000},
  {path: 'missing/README.md', type: 'file'},
  {path: 'notebooks/new.ipynb', type: 'file', mtime: 9990},
];
_sidebarLogRecentDiagnostics(files, '/workspace/project', 'settings-save', 10000);
const rows = events
  .filter(event => event.details && event.details.event_type === 'sidebar.recent.readme')
  .map(event => JSON.parse(event.message.replace('recent README diagnostic ', '')));
const summaryEvent = events.find(event => event.details && event.details.event_type === 'sidebar.recent.summary');
process.stdout.write(JSON.stringify({
  summary: JSON.parse(summaryEvent.message.replace('recent files diagnostic ', '')),
  rows,
  flushed: events.some(event => event.level === 'flush'),
}));
"""
    )

    assert result["summary"]["root"] == "/workspace/project"
    assert result["summary"]["recent_minutes"] == 60
    assert result["summary"]["file_count"] == 4
    assert result["summary"]["files_with_mtime"] == 3
    assert result["summary"]["recent_count"] == 2
    assert result["summary"]["readme_count"] == 3
    assert [(row["path"], row["result"]) for row in result["rows"]] == [
        ("repositories/queries/README.md", "included"),
        ("docs/README.md", "outside_freshness_window"),
        ("missing/README.md", "missing_mtime"),
    ]
    assert result["flushed"] is True


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
const window = {};
const currentProject = {path: '/workspace/project'};
const esc = value => String(value);
const escAttr = value => String(value);
const symlinkClass = () => '';
const symlinkTitle = () => '';
const symlinkMarker = () => '';
const fileIconHtml = () => '<i></i>';
const _treeIsOpen = () => true;
const historyCalls = [];
const openExplorerHistory = ctx => historyCalls.push(ctx);
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
openSidebarFileHistory('core/tests/test_project_routes.py');
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
    html.includes('sidebar-git-history'),
    html.includes('including uncommitted changes'),
  ],
  historyCall: historyCalls[0],
}));
"""
    )

    assert result == {
        "root": ["core"],
        "coreChildren": ["src/core", "tests"],
        "sourceChildren": ["routes", "static/js"],
        "isolated": ["alpha/beta/gamma"],
        "rendered": [True, True, True, True, True, True],
        "historyCall": {
            "kind": "file",
            "path": "core/tests/test_project_routes.py",
            "root": "/workspace/project",
            "row": None,
            "surface": "project",
        },
    }


def test_recent_git_status_badge_precedes_permanent_history_action() -> None:
    helper = _between(
        "function _sidebarPlaceGitBadge(row, badge)",
        "function _sidebarApplyGitStatus(entry)",
    )
    result = _run_node(
        helper
        + """
const badge = {name: 'status'};
const actions = {name: 'history'};
const row = {
  children: [actions, badge],
  querySelector(selector) {
    return selector === '.sidebar-actions' ? actions : null;
  },
  insertBefore(node, reference) {
    this.children = this.children.filter(child => child !== node);
    this.children.splice(this.children.indexOf(reference), 0, node);
  },
  appendChild(node) {
    this.children = this.children.filter(child => child !== node);
    this.children.push(node);
  },
};
_sidebarPlaceGitBadge(row, badge);
process.stdout.write(JSON.stringify(row.children.map(child => child.name)));
"""
    )

    assert result == ["status", "history"]


def test_sidebar_config_modal_and_all_sidebar_surfaces_are_wired() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    template = INDEX.read_text(encoding="utf-8")

    for element_id in (
        "sidebarFileConfigModal",
        "sidebarConfigHidden",
        "sidebarConfigRecent",
        "sidebarConfigFreshness",
        "sidebarConfigExtensions",
        "sidebarConfigWorktreeFolder",
        "sidebarConfigWorktreeStatus",
        "sidebarConfigWorktreeColors",
    ):
        assert f'id="{element_id}"' in template

    assert '<option value="120">2 hours</option>' in template
    assert '<option value="4320">3 days</option>' in template
    assert '<option value="10080">' not in template
    assert '<option value="43200">' not in template

    # Repository, project, framework, and workspace sidebar renderers all use
    # the same settings entry point instead of four divergent checkboxes.
    assert source.count("_sidebarFileConfigButtonHtml()") >= 4
    assert "Show hidden files</label>" not in source
    assert source.count("_sidebarRecentSectionHtml(") >= 4
    assert source.count("_sidebarWorktreePickerHtml(") >= 5
    assert "SIDEBAR_WORKTREE_DEFAULT_COLOR = '#6e7681'" in source


def test_project_mtime_poll_is_single_flight_and_backs_off_after_503() -> None:
    poller = _between(
        "// Auto-refresh project view when any file in the project folder changes",
        "// Sidebar git decorations poll.",
    )
    result = _run_node(
        """
let tick = null;
let now = 10_000;
let fetchCalls = 0;
const releases = [];
Date.now = () => now;
const UI_CHECK = false;
const document = {
  hidden: false,
  body: {classList: {contains() { return false; }}},
};
const currentProject = {is_project: true, path: '/workspace/project'};
const currentRepo = null;
const _projDocEditing = false;
const _projDocPath = null;
function setInterval(callback) { tick = callback; }
function fetch() {
  fetchCalls += 1;
  return new Promise(resolve => releases.push(resolve));
}
function response(status, body) {
  return {ok: status >= 200 && status < 300, status, json: async () => body};
}
"""
        + poller
        + """
(async () => {
  const first = tick();
  const overlap = tick();
  const callsWhilePending = fetchCalls;
  releases.splice(0).forEach(resolve => resolve(response(503, {detail: 'busy'})));
  await Promise.all([first, overlap]);

  now += 1_000;
  const earlyRetry = tick();
  const callsDuringBackoff = fetchCalls;
  releases.splice(0).forEach(resolve => resolve(response(503, {detail: 'busy'})));
  await earlyRetry;

  now += 1_500;
  const retry = tick();
  const callsAfterBackoff = fetchCalls;
  releases.splice(0).forEach(resolve => resolve(response(200, {mtime: 123})));
  await retry;

  process.stdout.write(JSON.stringify({
    callsWhilePending,
    callsDuringBackoff,
    callsAfterBackoff,
  }));
})().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""
    )

    assert result == {
        "callsWhilePending": 1,
        "callsDuringBackoff": 1,
        "callsAfterBackoff": 2,
    }
