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
LAB_SHELL_CSS = ROOT / "core/src/core/static/css/lab-shell.css"


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


def test_framework_top_tab_is_labeled_home() -> None:
    source = LAB_APP.read_text(encoding="utf-8")

    assert '<span class="label">&#x1F3E0; Home</span>' in source
    assert 'document.title = \'Home\'' in source


def test_sidebar_tree_indentation_has_no_depth_cap() -> None:
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")

    assert (
        ".sidebar-folder-children { display: none; position: relative; "
        "padding-left: 16px; }"
    ) in css
    assert ".sidebar-folder-children.open::before" in css
    assert ".sidebar-folder-children .sidebar-folder-children .sidebar-file" not in css
    assert ".sidebar-folder-children .sidebar-folder-children.open::before" not in css


def test_project_server_iframe_carries_its_workspace_in_the_mount_path() -> None:
    source = LAB_APP.read_text(encoding="utf-8")

    assert "function _proxyMountPath(projectId, name, workspaceId = null)" in source
    assert "/api/workspace-proxy/${encodeURIComponent(workspaceId)}" in source
    assert "_projectWorkspaceId(currentProject)" in source
    assert "if (project.workspace) return project.workspace;" in source


def test_terminal_sessions_support_independent_orientation_and_detail() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert '<div class="term-stage">' in html
    assert 'id="termSessionList" role="tablist"' in html
    assert 'aria-orientation="vertical"' in html
    assert 'id="termActiveSession"' in html
    assert 'ondblclick="termRenameCurrent()"' in html
    assert 'onclick="termToggleSessionOrientation()"' in html
    assert 'onclick="termToggleSessionDetail()"' in html
    assert ".term-stage { display: flex; flex: 1;" in css
    assert ".term-sessions { display: flex; flex-direction: column;" in css
    assert "width: 62px" in css
    assert "overflow-y: auto" in css
    assert ".term-panel.term-sessions-horizontal .term-stage" in css
    assert ".term-panel.term-sessions-full .term-sessions" in css
    assert ".term-panel.term-sessions-horizontal.term-sessions-full" in css
    assert 'class="sess-icon"' in source
    assert 'class="sess-order"' in source
    assert 'class="agent"' in source
    assert 'class="sess-label' in source
    assert 'class="k"' in source
    assert "(e.clientY - rect.top) < rect.height / 2" in source
    assert "(e.clientX - rect.left) < rect.width / 2" in source
    assert 'aria-selected="${active ? \'true\' : \'false\'}"' in source


def test_terminal_tabs_show_recent_activity_with_configurable_window() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert 'id="termRecentSettingsBtn"' in html
    assert 'onclick="termToggleRecentSettings(event)"' in html
    assert '<select id="termRecentMinutes"' in html
    assert 'onchange="termSetRecentMinutes(this.value)"' in html
    assert '<option value="15">15 minutes</option>' in html
    assert '<option value="180">3 hours</option>' in html
    assert 'id="termRecentColor" type="color"' in html
    assert 'oninput="termSetRecentColor(this.value)"' in html
    assert "const _TERM_RECENT_MINUTES_KEY = 'labTermRecentMinutes'" in source
    assert "const _TERM_RECENT_COLOR_KEY = 'labTermRecentColor'" in source
    assert "const _TERM_RECENT_ACTIVITY_KEY = 'labTermRecentActivity-v1'" in source
    assert "function _termMarkRecent(projectId, sessionName" in source
    assert "function _termSessionRecentMeta(session, now = Date.now())" in source
    assert "const recent = recentMeta ? ' recent' : '';" in source
    assert "_termMarkRecent(prevProjectId, prev);" in source
    assert "_termMarkRecent(projectId, name);" in source
    assert ".term-sessions .sess.recent:not(.active)" in css
    assert ".term-sessions .sess.recent:not(.active)::after" not in css
    assert ".term-sessions .sess.recent:not(.active) { box-shadow: inset 3px 0 0" in css
    assert ".term-panel.term-sessions-horizontal .term-sessions .sess.recent:not(.active)" not in css
    assert "var(--term-recent-color, var(--green))" in css
    assert ".term-recent-btn-swatch" in css


def test_terminal_recent_activity_is_scoped_persisted_and_expires() -> None:
    recent_helpers = _js_between(
        "function _termNormalizeRecentMinutes(value)",
        "let _termRecentSettingsOutside",
    )
    result = _run_node(
        """
const stored = {};
const localStorage = {
  setItem(key, value) { stored[key] = value; },
};
const _TERM_RECENT_ACTIVITY_KEY = 'recent';
const _TERM_RECENT_MINUTES_KEY = 'minutes';
const _TERM_RECENT_COLOR_KEY = 'color';
const _TERM_RECENT_MINUTE_OPTIONS = [15, 30, 60, 180, 360, 720, 1440];
let termRecentMinutes = 60;
let termRecentColor = '#3fb950';
let termRecentActivity = {};
let workspace = 'ssd';
let termSessions = [{name: 'tmux-codex', logical_name: 'codex'}];
let renderCount = 0;
function makeElement(value = '') {
  return {
    value,
    textContent: '',
    title: '',
    style: {
      values: {},
      setProperty(key, next) { this.values[key] = next; },
    },
  };
}
const elements = {
  termRecentSettingsBtn: makeElement(),
  termRecentButtonLabel: makeElement(),
  termRecentMinutes: makeElement('60'),
  termRecentColor: makeElement('#3fb950'),
  termRecentColorValue: makeElement(),
  termPanel: makeElement(),
};
const document = {getElementById(id) { return elements[id] || null; }};
function _termSessionsKey(project, workspaceId) { return workspaceId + '::' + project; }
function _termActiveProjectId() { return 'demo'; }
function _termWorkspaceId() { return workspace; }
function termRenderSessionList() { renderCount += 1; }
""" + recent_helpers + """
const now = 10_000_000;
_termMarkRecent('demo', 'tmux-codex', 'ssd', now - 50 * 60 * 1000);
const recentAt60 = _termSessionRecentMeta(termSessions[0], now);
termRecentMinutes = 30;
const recentAt30 = _termSessionRecentMeta(termSessions[0], now);
workspace = 'other';
const otherWorkspace = _termSessionRecentMeta(termSessions[0], now);
termSetRecentMinutes(180);
termSetRecentColor('#A371F7');
process.stdout.write(JSON.stringify({
  recentAt60,
  recentAt30,
  otherWorkspace,
  stored: JSON.parse(stored.recent),
  normalized: [
    _termNormalizeRecentMinutes(0),
    _termNormalizeRecentMinutes(61.7),
    _termNormalizeRecentMinutes(2000),
    _termNormalizeRecentMinutes('invalid'),
  ],
  normalizedColors: [
    _termNormalizeRecentColor('#ABCDEF'),
    _termNormalizeRecentColor('invalid'),
  ],
  settings: {
    storedMinutes: stored.minutes,
    storedColor: stored.color,
    buttonLabel: elements.termRecentButtonLabel.textContent,
    selectedMinutes: elements.termRecentMinutes.value,
    colorInput: elements.termRecentColor.value,
    colorText: elements.termRecentColorValue.textContent,
    panelColor: elements.termPanel.style.values['--term-recent-color'],
    renderCount,
  },
}));
"""
    )

    assert result["recentAt60"]["label"] == "used 50m ago"
    assert result["recentAt30"] is None
    assert result["otherWorkspace"] is None
    assert result["stored"] == {"ssd::demo": {"codex": 7_000_000}}
    assert result["normalized"] == [15, 60, 1440, 60]
    assert result["normalizedColors"] == ["#abcdef", "#3fb950"]
    assert result["settings"] == {
        "storedMinutes": "180",
        "storedColor": "#a371f7",
        "buttonLabel": "3h",
        "selectedMinutes": "180",
        "colorInput": "#a371f7",
        "colorText": "#a371f7",
        "panelColor": "#a371f7",
        "renderCount": 2,
    }


def test_terminal_tabs_support_colored_dividers() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert 'id="termCreateDividerBtn"' in html
    assert 'onclick="termCreateDivider()"' in html
    assert 'id="termCreateGroupBtn"' not in html
    assert 'id="termGroupBtn"' not in html
    assert 'id="termRenameBtn"' not in html
    assert 'ondblclick="termRenameCurrent()"' in html
    assert 'id="termGroupMenu"' in html
    assert "const _TERM_GROUPS_KEY = 'labTermGroups-v1'" in source
    assert "function termCreateDivider(sessionName = termCurrentSession)" in source
    assert "function _termReconcileGroupOrder(state)" in source
    assert "function termReorderItems(srcToken, dstToken, placeBefore)" in source
    assert "function termAssignSessionGroup" not in source
    assert "function termToggleGroup" not in source
    assert "function termRenameGroup" not in source
    assert "function termOpenDividerOptions(groupId, anchor)" in source
    assert 'class="term-divider-section"' in source
    assert 'class="term-divider"' in source
    assert 'data-divider-options="${termSessEsc(divider.id)}"' in source
    assert 'data-order-token="${termSessEsc(`g:${divider.id}`)}"' in source
    assert 'data-order-token="${termSessEsc(`s:${logical}`)}"' in source
    assert ".term-divider::before" in css
    assert ".term-panel.term-sessions-horizontal .term-divider" in css
    assert ".term-sessions .sess.grouped::before" not in css
    assert ".term-group-caret" not in css
    assert ".term-group-color.selected" in css


def test_terminal_divider_state_is_scoped_and_persisted_in_browser() -> None:
    group_helpers = _js_between(
        "function _termGroupScopeKey()",
        "function _termSessionDisplay(s)",
    )
    result = _run_node(
        """
const stored = {};
const localStorage = {
  getItem(key) { return Object.prototype.hasOwnProperty.call(stored, key) ? stored[key] : null; },
  setItem(key, value) { stored[key] = value; },
};
const document = {
  getElementById() { return null; },
  removeEventListener() {},
  addEventListener() {},
};
const window = {innerWidth: 1200, innerHeight: 800};
const _TERM_GROUPS_KEY = 'groups';
const _TERM_GROUP_COLORS = ['#58a6ff', '#a371f7'];
let _termGroupMenuOutside = null;
let termSessions = [{name: 'tmux-one', logical_name: 'codex'}];
let renderCount = 0;
function _termSessionsKey(project, workspace) { return workspace + '::' + project; }
function _termActiveProjectId() { return 'demo'; }
function _termWorkspaceId() { return 'ssd'; }
function _termSessionMeta(name) { return termSessions.find(item => item.name === name) || null; }
function termRenderSessionList() { renderCount += 1; }
function termSessEsc(value) { return String(value); }
""" + group_helpers + """
termCreateDivider('tmux-one');
const state = _termReadGroupState();
process.stdout.write(JSON.stringify({
  keys: Object.keys(JSON.parse(stored.groups)),
  color: state.groups[0].color,
  order: state.order,
  membership: state.membership,
  renderCount,
}));
"""
    )

    assert result["keys"] == ["ssd::demo"]
    assert result["color"] == "#58a6ff"
    assert result["order"][0].startswith("g:")
    assert result["order"][1] == "s:codex"
    assert result["membership"] == {}
    assert result["renderCount"] == 1


def test_terminal_divider_order_is_reconciled_with_live_sessions() -> None:
    group_helpers = _js_between(
        "function _termGroupScopeKey()",
        "function _termSessionDisplay(s)",
    )
    result = _run_node(
        """
const localStorage = {getItem() { return null; }, setItem() {}};
const document = {getElementById() { return null; }, removeEventListener() {}, addEventListener() {}};
const window = {innerWidth: 1200, innerHeight: 800};
const _TERM_GROUPS_KEY = 'groups';
const _TERM_GROUP_COLORS = ['#58a6ff', '#a371f7'];
let _termGroupMenuOutside = null;
let termSessions = [
  {name: 'tmux-one', logical_name: 'one'},
  {name: 'tmux-two', logical_name: 'two'},
  {name: 'tmux-three', logical_name: 'three'},
];
function _termSessionsKey(project, workspace) { return workspace + '::' + project; }
function _termActiveProjectId() { return 'demo'; }
function _termWorkspaceId() { return 'ssd'; }
function _termSessionMeta(name) { return termSessions.find(item => item.name === name) || null; }
function termRenderSessionList() {}
function termSessEsc(value) { return String(value); }
""" + group_helpers + """
const state = {
  groups: [
    {id: 'research', name: 'Research', color: '#58a6ff', collapsed: false},
    {id: 'build', name: 'Build', color: '#a371f7', collapsed: false},
  ],
  order: ['s:one', 'g:research', 's:two', 'g:build', 's:three'],
  membership: {},
};
process.stdout.write(JSON.stringify({
  order: _termReconcileGroupOrder(state),
}));
"""
    )

    assert result == {
        "order": ["s:one", "g:research", "s:two", "g:build", "s:three"]
    }


def test_terminal_agent_activity_scraping_and_attention_ui_are_removed() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")

    assert "/api/term/sessions/status" not in source
    assert "/api/term/projects-attention" not in source
    assert "termStartStatusPolling" not in source
    assert ".term-sessions .sess .stat" not in css


def test_terminal_session_view_controls_persist_independently() -> None:
    view_helpers = _js_between(
        "function _termApplySessionView(refit = true)",
        "// Same TDZ hoist for the files-sidebar",
    )
    result = _run_node(
        """
const classes = new Set();
const stored = {};
const panel = {classList: {toggle(value, on) {
  if (on) classes.add(value); else classes.delete(value);
}}};
function makeButton() {
  return {textContent: '', title: '', attrs: {}, setAttribute(name, value) { this.attrs[name] = value; }};
}
const orientationBtn = makeButton();
const detailBtn = makeButton();
const sessionList = makeButton();
const document = {getElementById(id) {
  if (id === 'termPanel') return panel;
  if (id === 'termSessionList') return sessionList;
  if (id === 'termOrientationBtn') return orientationBtn;
  if (id === 'termDetailBtn') return detailBtn;
  return null;
}};
const localStorage = {setItem(key, value) { stored[key] = value; }};
const _TERM_SESSION_ORIENTATION_KEY = 'orientation';
const _TERM_SESSION_DETAIL_KEY = 'detail';
let termSessionOrientation = 'vertical';
let termSessionDetail = 'compact';
function requestAnimationFrame() {}
""" + view_helpers + """
termToggleSessionOrientation();
termToggleSessionDetail();
process.stdout.write(JSON.stringify({
  classes: Array.from(classes).sort(),
  stored,
  orientationText: orientationBtn.textContent,
  orientationPressed: orientationBtn.attrs['aria-pressed'],
  detailText: detailBtn.textContent,
  detailPressed: detailBtn.attrs['aria-pressed'],
  ariaOrientation: sessionList.attrs['aria-orientation'],
}));
"""
    )

    assert result["classes"] == ["term-sessions-full", "term-sessions-horizontal"]
    assert result["stored"] == {"orientation": "horizontal", "detail": "full"}
    assert result["orientationText"] == "↕"
    assert result["orientationPressed"] == "true"
    assert result["detailText"] == "◉"
    assert result["detailPressed"] == "true"
    assert result["ariaOrientation"] == "horizontal"


def test_terminal_active_session_details_move_to_header() -> None:
    header_helpers = _js_between(
        "function _termSessionDisplay(s)",
        "function termRenderSessionList()",
    )
    result = _run_node(
        """
const activeHeader = {
  className: '', title: '', innerHTML: '',
  style: {setProperty() {}, removeProperty() {}},
  removeAttribute(name) { if (name === 'title') this.title = ''; },
};
const document = {getElementById(id) {
  if (id === 'termActiveSession') return activeHeader;
  return null;
}};
const termSessions = [{
  name: 'lab-demo-codex-2-abc123', logical_name: 'codex-2',
  kind: 'claude', agent: 'codex',
  label: 'Sessions', summary: 'stale pane prompt',
  agent_session_name: 'Review terminal naming',
  agent_session_requests: [
    'Inspect the tab metadata',
    'Show the latest task in hover and header',
  ],
}];
let termCurrentSession = termSessions[0].name;
let termCurrentProjectId = 'demo';
function _termActiveProjectId() { return 'demo'; }
function termSessEsc(value) { return String(value); }
function prompt() { return null; }
""" + header_helpers + """
_termRenderActiveSessionHeader();
process.stdout.write(JSON.stringify({
  className: activeHeader.className,
  html: activeHeader.innerHTML,
}));
"""
    )

    assert result["className"] == "term-active-session on claude"
    assert '<span class="name">Sessions</span>' in result["html"]
    assert (
        '<span class="summary">Requests · Show the latest task in hover and header</span>'
        in result["html"]
    )
    assert '<span class="agent">codex</span>' in result["html"]


def test_terminal_request_block_keeps_history_in_a_three_item_viewport() -> None:
    header_helpers = _js_between(
        "function _termSessionDisplay(s)",
        "function _termSessionPillHtml(s, index)",
    )
    result = _run_node(
        """
const activeHeader = {
  className: '', title: '', innerHTML: '',
  removeAttribute() {},
};
const statusSummary = {
  title: '', hidden: true,
  removeAttribute(name) { if (name === 'title') this.title = ''; },
};
const statusSummaryLabel = {textContent: ''};
const statusSummaryText = {
  textContent: '', innerHTML: '', scrollTop: 0, scrollHeight: 240,
};
const document = {getElementById(id) {
  if (id === 'termActiveSession') return activeHeader;
  if (id === 'termStatusSummary') return statusSummary;
  if (id === 'termStatusSummaryLabel') return statusSummaryLabel;
  if (id === 'termStatusSummaryText') return statusSummaryText;
  return null;
}};
const termSessions = [{
  name: 'tmux-codex', logical_name: 'codex', agent: 'codex',
  agent_session_name: 'Session names',
  agent_session_requests: [
    'Inspect the existing header',
    'Fix immediate hover',
    'Show this task above the terminal',
    'Keep every request in the current session',
  ],
}];
let termCurrentSession = 'tmux-codex';
let termCurrentProjectId = 'demo';
function _termActiveProjectId() { return 'demo'; }
function termSessEsc(value) { return String(value); }
""" + header_helpers + """
_termRenderActiveSessionHeader();
process.stdout.write(JSON.stringify({statusSummary, statusSummaryLabel, statusSummaryText}));
"""
    )

    assert result["statusSummary"] == {"title": "", "hidden": False}
    assert result["statusSummaryLabel"]["textContent"] == "Requests"
    assert result["statusSummaryText"]["innerHTML"].count(
        'class="term-context-row"'
    ) == 4
    assert "Inspect the existing header" in result["statusSummaryText"]["innerHTML"]
    assert "Fix immediate hover" in result["statusSummaryText"]["innerHTML"]
    assert "Keep every request in the current session" in (
        result["statusSummaryText"]["innerHTML"]
    )
    assert result["statusSummaryText"]["scrollTop"] == 240

    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    status_end = html.index('</div>', html.index('id="termStatus"'))
    assert html.index('id="termStatusSummary"') > status_end
    assert 'id="termStatusSummaryLabel"' in html
    assert 'id="termStatusSummaryText"' in html
    assert ">Requests</span>" in html
    assert "grid-template-columns: 56px minmax(0, 1fr)" in css
    assert "max-height: min(24vh, calc(8.4em + 14px))" in css
    assert "max-height: min(34vh, calc(13.5em + 28px))" in css
    assert "overflow-y: auto" in css
    assert "-webkit-line-clamp: 2" in css


def test_terminal_custom_tooltip_opens_synchronously_without_native_title() -> None:
    tooltip_helpers = _js_between(
        "function _termContextRowsHtml(context)",
        "function _termSessionPillHtml(s, index)",
    )
    result = _run_node(
        """
const tooltip = {
  hidden: true, innerHTML: '', style: {},
  addEventListener(name) { this['on' + name] = true; },
  getBoundingClientRect() { return {width: 220, height: 80}; },
};
const payload = JSON.stringify({
  label: 'Requests', items: ['Old request', 'Latest task', 'Another request', 'Newest request'],
  isObjective: false, meta: ['tmux-name', 'Double-click to rename'],
});
const anchor = {
  getAttribute(name) {
    return name === 'data-tooltip' ? payload : null;
  },
  getBoundingClientRect() {
    return {left: 20, right: 70, top: 30, width: 50, height: 36};
  },
};
const document = {getElementById(id) {
  return id === 'termSessionTooltip' ? tooltip : null;
}};
const window = {innerWidth: 900, innerHeight: 700};
function termSessEsc(value) { return String(value); }
""" + tooltip_helpers + """
_termShowSessionTooltip(anchor);
process.stdout.write(JSON.stringify(tooltip));
"""
    )

    assert result["hidden"] is False
    assert "term-session-tooltip-label\">Requests" in result["innerHTML"]
    assert "Old request" in result["innerHTML"]
    assert "Latest task" in result["innerHTML"]
    assert "Another request" in result["innerHTML"]
    assert "Newest request" in result["innerHTML"]
    assert "tmux-name" in result["innerHTML"]
    assert result["style"] == {"left": "78px", "top": "30px"}
    assert result["onpointerenter"] is True
    assert result["onpointerleave"] is True

    source = LAB_APP.read_text(encoding="utf-8")
    pill = _js_between(
        "function _termSessionPillHtml(s, index)",
        "function termRenderSessionList()",
    )
    assert 'data-tooltip="${termSessEsc(tooltip)}"' in pill
    assert "_termSessionTooltipPayload" in pill
    assert "node.addEventListener('pointerenter'" in source
    assert "node.addEventListener('pointerleave', _termScheduleSessionTooltipHide)" in source


def test_terminal_context_viewport_uses_exact_newest_row_count() -> None:
    helper = _js_between(
        "function _termShowNewestContextItems(container, visibleCount)",
        "function _termSessionSummary(s)",
    )
    result = _run_node(
        helper
        + """
const rows = [
  {offsetTop: 0, offsetHeight: 14},
  {offsetTop: 21, offsetHeight: 28},
  {offsetTop: 56, offsetHeight: 14},
  {offsetTop: 77, offsetHeight: 28},
  {offsetTop: 112, offsetHeight: 14},
  {offsetTop: 133, offsetHeight: 28},
];
const container = {
  style: {maxHeight: 'old'}, scrollTop: 0, scrollHeight: 220,
  querySelectorAll() { return rows; },
};
_termShowNewestContextItems(container, 3);
process.stdout.write(JSON.stringify(container));
"""
    )

    assert result["style"]["maxHeight"] == "84px"
    assert result["scrollTop"] == 220


def test_terminal_session_name_avoids_stale_generated_titles() -> None:
    display_helper = _js_between(
        "function _termSessionDisplay(s)",
        "function _termSessionVisual(s)",
    )
    result = _run_node(
        display_helper + """
process.stdout.write(JSON.stringify({
  generated: _termSessionDisplay({
    name: 'tmux-name', logical_name: 'codex-3',
    agent_session_name: 'Generated session title',
  }),
  manual: _termSessionDisplay({
    name: 'tmux-name', logical_name: 'codex-3',
    agent_session_name: 'Generated session title', label: 'My tab',
  }),
  stale: _termSessionDisplay({
    name: 'tmux-name', logical_name: 'codex-3',
    agent_session_name: 'Old generated title',
    agent_session_requests: ['First task', 'New task'],
  }),
  fallback: _termSessionDisplay({name: 'tmux-name', logical_name: 'codex-3'}),
}));
"""
    )

    assert result == {
        "generated": "Generated session title",
        "manual": "My tab",
        "stale": "codex-3",
        "fallback": "codex-3",
    }


def test_terminal_hover_scrolls_all_requests_or_uses_current_ai_objective() -> None:
    title_helpers = _js_between(
        "function _termSessionDisplay(s)",
        "async function termRenameSession(name)",
    )
    result = _run_node(
        title_helpers + """
const requests = JSON.parse(_termSessionTooltipPayload({
  name: 'tmux-name', logical_name: 'codex-2', label: 'Sessions',
  agent_session_name: 'Terminal naming',
  agent_session_requests: [
    'Inspect the current metadata',
    'Show the latest user assignment',
    'Keep the complete session history',
    'Make each preview two lines',
  ],
  summary: 'Ask Codex to do anything',
}, 'Recently active'));
const objective = JSON.parse(_termSessionTooltipPayload({
  name: 'tmux-objective', logical_name: 'claude-2',
  agent_session_objective: 'AI-written current objective',
  agent_session_requests: ['Old request', 'Newest request'],
}, ''));
process.stdout.write(JSON.stringify({requests, objective}));
"""
    )

    assert result["requests"] == {
        "label": "Requests",
        "items": [
            "Inspect the current metadata",
            "Show the latest user assignment",
            "Keep the complete session history",
            "Make each preview two lines",
        ],
        "isObjective": False,
        "meta": ["tmux-name", "Recently active", "Double-click to rename"],
    }
    assert result["objective"] == {
        "label": "Objective",
        "items": ["AI-written current objective"],
        "isObjective": True,
        "meta": ["tmux-objective", "Double-click to rename"],
    }


def test_workspace_view_opens_its_own_terminal_scope() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    term_open = _js_between(
        "async function termOpenForWorkspace()",
        "// ─── Workspace view",
    )
    result = _run_node(
        """
const classes = new Set(['workspace-active']);
const calls = [];
const WORKSPACE_PROJECT_ID = '__workspace__';
const document = {body: {classList: {
  add(value) { classes.add(value); },
  contains(value) { return classes.has(value); },
}}};
function _termIsScopeActive(pid) { return pid === WORKSPACE_PROJECT_ID; }
function _termApplyRememberedVisibility() { calls.push('visibility'); }
async function _termTryWarmOpen(pid) { calls.push('warm:' + pid); return false; }
async function _termRestoreSessionsForProject(pid) { calls.push('restore:' + pid); }
function termStartPeriodicRefresh() { calls.push('refresh'); }
""" + term_open + """
(async () => {
  await termOpenForWorkspace();
  process.stdout.write(JSON.stringify({calls, termOpen: classes.has('term-open')}));
})().catch((err) => { console.error(err && err.stack || err); process.exit(1); });
"""
    )

    assert result["termOpen"] is True
    assert result["calls"] == [
        "visibility",
        "warm:__workspace__",
        "restore:__workspace__",
        "refresh",
    ]
    assert "if (!UI_CHECK) termOpenForWorkspace();" in source


def test_terminal_new_menu_hides_workspace_disabled_agents() -> None:
    refresh_agent_avail = _js_between(
        "let _agentAvail = null;",
        "// ─── File ↔ terminal links",
    )
    result = _run_node(
        """
const buttons = ['claude', 'codex', 'copilot'].map(agent => ({
  dataset: {agent}, hidden: false, disabled: false, style: {}, textContent: agent,
}));
const picker = {querySelectorAll() { return buttons; }};
async function loadWorkspaceAgentPolicy() {
  return {supported: ['codex'], default: 'codex'};
}
async function fetch() {
  return {json: async () => ({claude: true, codex: true, copilot: false})};
}
""" + refresh_agent_avail + """
(async () => {
  await termRefreshAgentAvail(picker);
  process.stdout.write(JSON.stringify(buttons));
})().catch((err) => { console.error(err && err.stack || err); process.exit(1); });
"""
    )

    by_agent = {row["dataset"]["agent"]: row for row in result}
    assert by_agent["claude"]["hidden"] is True
    assert by_agent["copilot"]["hidden"] is True
    assert by_agent["codex"]["hidden"] is False
    assert by_agent["codex"]["disabled"] is False


def test_terminal_new_menu_opens_a_grouped_tmux_session_modal() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert 'onclick="termOpenAttachModal(event)"' in html
    assert 'id="termAttachModal"' in html
    assert 'aria-labelledby="termAttachModalTitle"' in html
    assert 'id="termAttachFilter" type="search"' in html
    assert 'id="termAttachList" onclick="termChooseAttachCandidate(event)"' in html
    assert 'id="termAttachName"' not in html
    assert ".form-modal.term-attach-modal" in css
    assert ".term-attach-project.current" in css
    assert ".term-attach-badge.live" in css
    assert ".term-attach-row.has-tab:disabled" in css
    assert "/api/term/sessions/attachable?${query}" in source
    assert "_termAttachModalScope = {projectId, workspaceId, projectLabel};" in source
    assert "const heading = hasUiTab ? 'Attached in Lab' : 'Available to attach';" in source
    assert "const disabled = hasUiTab || _termAttachPendingName;" in source
    assert "Client attached" not in _js_between(
        "function termRenderAttachModal()",
        "async function termReloadAttachModal()",
    )


def test_file_terminal_link_modal_offers_new_and_existing_sessions() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = LAB_SHELL_CSS.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert 'id="termLinkModal"' in html
    assert 'id="termLinkNew"' in html
    assert 'id="termLinkList"' in html
    assert "termCreateLinkedSession('claude','claude')" in html
    assert "termCreateLinkedSession('claude','codex')" in html
    assert "termCreateLinkedSession('claude','copilot')" in html
    assert "termCreateLinkedSession('terminal')" in html
    assert ".form-modal.term-link-modal" in css
    assert ".term-link-choice-badge.linked" in css
    assert "async function termOpenLinkModal(ctx)" in source
    assert "async function termLinkExistingSession(sessionName)" in source
    assert "name: state.fileName" in source
    assert "linked_file: linkedFile" in source
    assert source.count("const clipboardCopy = _termCopyLinkedAbsolutePath(state);") == 2
    assert "Absolute path copied" in source


def test_linked_file_identity_normalizes_only_the_root_suffix() -> None:
    helpers = _js_between(
        "function _termNormalizeLinkedRoot(value)",
        "function _termSetLinkStatus(message, error = false)",
    )
    result = _run_node(helpers + """
const linked = {root: '/workspace/project///', path: 'notebooks/analysis.ipynb'};
process.stdout.write(JSON.stringify({
  same: _termLinkedFileMatches(linked, '/workspace/project', 'notebooks/analysis.ipynb'),
  differentFile: _termLinkedFileMatches(linked, '/workspace/project', 'notebooks/other.ipynb'),
  differentRoot: _termLinkedFileMatches(linked, '/workspace/other', 'notebooks/analysis.ipynb'),
  label: _termLinkedFileLabel(linked),
  basename: _termLinkedFileName(linked.path),
  absolute: _termLinkedAbsolutePath(linked.root, linked.path),
  rootAbsolute: _termLinkedAbsolutePath('/', './analysis.ipynb'),
}));
""")

    assert result == {
        "same": True,
        "differentFile": False,
        "differentRoot": False,
        "label": "notebooks/analysis.ipynb",
        "basename": "analysis.ipynb",
        "absolute": "/workspace/project/notebooks/analysis.ipynb",
        "rootAbsolute": "/analysis.ipynb",
    }


def test_linked_file_sync_is_opt_in_and_reveals_the_terminal_panel() -> None:
    sync_helper = _js_between(
        "function _termSyncFromFileClick(root, path)",
        "async function _termOpenLinkedFile(session)",
    )
    result = _run_node("""
const classes = new Set(['term-collapsed']);
const document = {body: {classList: {
  add(value) { classes.add(value); },
  remove(value) { classes.delete(value); },
}}};
let _linkedTerminalSyncOn = false;
let termCurrentSession = 'tmux-linked';
let termCurrentProjectId = 'demo';
let termSessions = [{name: 'tmux-linked', linked_file: {root: '/repo', path: 'a.ipynb'}}];
let attaches = [];
let remembered = [];
function _termActiveProjectId() { return 'demo'; }
function _termLinkedFileMatches(link, root, path) {
  return link && link.root === root && link.path === path;
}
function _termRememberVisibility(key, shown) { remembered.push([key, shown]); }
function _termVisibilityKey() { return 'demo-key'; }
function termAttach(name, project) { attaches.push([name, project]); }
""" + sync_helper + """
_termSyncFromFileClick('/repo', 'a.ipynb');
const whileOff = {classes: [...classes], attaches: [...attaches]};
_linkedTerminalSyncOn = true;
_termSyncFromFileClick('/repo', 'a.ipynb');
const active = {classes: [...classes], attaches: [...attaches], remembered: [...remembered]};
termCurrentSession = 'other';
_termSyncFromFileClick('/repo', 'a.ipynb');
process.stdout.write(JSON.stringify({whileOff, active, finalAttaches: attaches}));
""")

    assert "term-collapsed" in result["whileOff"]["classes"]
    assert result["whileOff"]["attaches"] == []
    assert "term-open" in result["active"]["classes"]
    assert "term-collapsed" not in result["active"]["classes"]
    assert result["active"]["attaches"] == []
    assert result["active"]["remembered"] == [["demo-key", True]]
    assert result["finalAttaches"] == [["tmux-linked", "demo"]]


def test_linked_terminal_sync_only_runs_from_explicit_file_or_terminal_clicks() -> None:
    source = LAB_APP.read_text(encoding="utf-8")
    repo_open = _js_between(
        "async function openProjectFile(filepath)",
        "function renderProjectFileView(filepath, fileContent)",
    )
    project_open = _js_between(
        "async function openProjectDoc(filepath",
        "function _proxyFromCachedSidebar(name)",
    )

    assert "_termSyncFromFileClick" not in repo_open
    assert "_termSyncFromFileClick" not in project_open
    assert source.count("_termSyncFromFileClick(") == 3
    assert source.count("onclick=\"openProjectDocFromFileClick(") == 3
    assert source.count("onclick=\"openProjectFileFromFileClick(") == 1
    assert "if (ctx.surface === 'repo') openProjectFile(ctx.path);" in source
    assert "else openProjectDoc(ctx.path, {root: ctx.root});" in source
    assert "const request = ++_termLinkedNavigationSeq;" in source
    assert "if (request !== _termLinkedNavigationSeq) return;" in source


def test_terminal_to_file_prefers_recent_row_then_files_tree() -> None:
    chooser = _js_between(
        "function _termPreferredLinkedSidebarRow(linked)",
        "function _termRevealLinkedSidebarRow(row)",
    )
    result = _run_node("""
function makeRow(id, classes, root, path) {
  return {
    id,
    classList: {contains(value) { return classes.includes(value); }},
    getAttribute(name) {
      if (name === 'data-entry-root') return root;
      if (name === 'data-entry-path') return path;
      return null;
    },
  };
}
const linked = {root: '/repo', path: 'notebooks/a.ipynb'};
const files = makeRow('files', ['sidebar-file'], '/repo', 'notebooks/a.ipynb');
const recent = makeRow('recent', ['sidebar-file', 'sidebar-file-recent'], '/repo', 'notebooks/a.ipynb');
const wrong = makeRow('wrong', ['sidebar-file-recent'], '/repo', 'notebooks/b.ipynb');
let rows = [files, wrong, recent];
const document = {querySelectorAll() { return rows; }};
function _termLinkedFileMatches(candidate, root, path) {
  return candidate.root === root && candidate.path === path;
}
""" + chooser + """
const withRecent = _termPreferredLinkedSidebarRow(linked).id;
rows = [files, wrong];
const filesFallback = _termPreferredLinkedSidebarRow(linked).id;
rows = [wrong];
const missing = _termPreferredLinkedSidebarRow(linked);
process.stdout.write(JSON.stringify({withRecent, filesFallback, missing}));
""")

    assert result == {
        "withRecent": "recent",
        "filesFallback": "files",
        "missing": None,
    }


def test_tmux_attach_modal_orders_current_project_unattached_sessions_first() -> None:
    ordering = _js_between(
        "function _termAttachProjectLabel(row)",
        "function _termAttachAge(row)",
    )
    result = _run_node(
        """
const SELF_PROJECT_ID = '__self__';
const CEREBRO_PROJECT_ID = '__cerebro__';
const WORKSPACE_PROJECT_ID = '__workspace__';
""" + ordering + """
const scope = {projectId: 'demo', workspaceId: 'main'};
const groups = _termAttachOrderedGroups([
  {name: 'other-free', logical_name: 'free', project_id: 'other', project_name: 'Other', workspace: 'main', has_ui_tab: false, created: 40},
  {name: 'demo-live', logical_name: 'live', project_id: 'demo', project_name: 'Demo', workspace: 'main', has_ui_tab: true, created: 50},
  {name: 'demo-free-old', logical_name: 'free-old', project_id: 'demo', project_name: 'Demo', workspace: 'main', has_ui_tab: false, created: 10},
  {name: 'demo-free-new', logical_name: 'free-new', project_id: 'demo', project_name: 'Demo', workspace: 'main', has_ui_tab: false, created: 30},
  {name: 'loose', logical_name: 'loose', project_id: null, project_name: 'Unassigned', workspace: null, has_ui_tab: false, created: 99},
], scope);
const filtered = _termAttachOrderedGroups(groups.flatMap(group => group.rows), scope, 'other');
process.stdout.write(JSON.stringify({
  projects: groups.map(group => group.projectName),
  current: groups.map(group => group.current),
  demoRows: groups[0].rows.map(row => [row.name, row.has_ui_tab]),
  filtered: filtered.map(group => group.projectName),
}));
"""
    )

    assert result == {
        "projects": ["Demo", "Other", "Unassigned"],
        "current": [True, False, False],
        "demoRows": [
            ["demo-free-new", False],
            ["demo-free-old", False],
            ["demo-live", True],
        ],
        "filtered": ["Other"],
    }


def test_tmux_attach_modal_selection_uses_captured_project_scope() -> None:
    attach_existing = _js_between(
        "async function termAttachExisting(rawSessionName)",
        "function termCreateNew(kind, agent)",
    )
    result = _run_node(
        """
const calls = [];
const attached = [];
const statuses = [];
let _termAttachModalScope = {projectId: 'demo', workspaceId: 'main', projectLabel: 'Demo'};
let _termAttachModalGeneration = 7;
let _termAttachPendingName = null;
let termSessions = [];
const _termSessionsCache = {set(key, value) { calls.push('cache:' + key + ':' + value.length); }};
function _termWorkspaceId() { return 'main'; }
function _termActiveProjectId() { return 'demo'; }
function _termIsScopeActive(pid) { return pid === 'demo'; }
function _termClearDead(name) { calls.push('clear:' + name); }
async function _termRefreshSessionsForProjectId(pid) { calls.push('refresh:' + pid); return true; }
function _termSessionsKey(pid, workspace) { return pid + ':' + workspace; }
function termRenderSessionList() { calls.push('render'); }
function termAttach(name, pid) { attached.push([name, pid]); }
function termSetStatus(kind, message) { statuses.push([kind, message]); }
function termRenderAttachModal() { calls.push('render-modal'); }
function _termSetAttachStatus(message, error = false) { statuses.push([error ? 'modal-err' : 'modal', message]); }
function termCloseAttachModal() { calls.push('close-modal'); _termAttachModalGeneration += 1; }
async function fetch(url, options) {
  calls.push({url, options, body: JSON.parse(options.body)});
  return {
    ok: true,
    json: async () => ({
      name: 'lab-demo-existing-work',
      logical_name: 'existing-work',
      project_id: 'demo',
      kind: 'attached',
    }),
  };
}
""" + attach_existing + """
(async () => {
  await termAttachExisting('  existing-work  ');
  process.stdout.write(JSON.stringify({calls, attached, statuses}));
})().catch((err) => { console.error(err && err.stack || err); process.exit(1); });
"""
    )

    request = next(call for call in result["calls"] if isinstance(call, dict))
    assert request["url"] == "/api/term/sessions/attach"
    assert request["options"]["method"] == "POST"
    assert request["body"] == {
        "project_id": "demo",
        "workspace": "main",
        "name": "existing-work",
    }
    assert result["attached"] == [["lab-demo-existing-work", "demo"]]
    assert "close-modal" in result["calls"]
    assert "refresh:demo" in result["calls"]


def test_attached_tmux_sessions_are_not_restored_as_plain_shells() -> None:
    source = LAB_APP.read_text(encoding="utf-8")

    assert "s.kind !== 'attached'" in source
    assert "The original tmux session will keep running." in source
    assert "session && session.attach_command" in source


def test_workspace_agents_card_writes_workspace_policy() -> None:
    source = LAB_APP.read_text(encoding="utf-8")

    assert "workspaceToggleAgent('${a}', this.checked, this)" in source
    assert "fetch('/api/workspace/agents', {" in source
    assert "Enabled agents appear in every <strong>+ New</strong> menu." in source
    assert "await termRefreshAgentAvail(el);" in source


def test_workspace_projects_card_can_create_in_owning_workspace() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = LAB_APP.read_text(encoding="utf-8")

    assert 'id="workspaceProjectModal"' in html
    assert 'id="workspaceProjectForm"' in html
    assert 'onclick="openWorkspaceProjectModal()">+ New project</button>' in source
    assert "fetch('/api/projects', {" in source
    assert "workspace: workspaceId" in source
    assert "projectsList = workspaces.flatMap(row => row.project_rows || []);" in source
    assert "goToProject(project.path);" in source


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
