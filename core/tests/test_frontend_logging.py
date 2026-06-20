from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which("node")


def _run_node(script: str) -> dict:
    if NODE is None:
        pytest.skip("node is required for frontend logging tests")
    proc = subprocess.run(
        [NODE, "-e", script],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _browser_harness(extra_js: str) -> str:
    return f"""
const fs = require('fs');
const vm = require('vm');

const code = fs.readFileSync('core/src/core/static/js/lib/error-report.js', 'utf8');
const uploads = [];
const nativeCalls = [];
let now = 100;
const listeners = {{ window: {{}}, document: {{}} }};

async function nativeFetch(input, opts = {{}}) {{
  nativeCalls.push({{ input: String(input), opts }});
  if (String(input) === '/api/log/client') {{
    const parsed = JSON.parse(String(opts.body || '{{}}'));
    if (Array.isArray(parsed.events)) uploads.push(parsed);
  }}
  return {{
    ok: true,
    status: 200,
    headers: {{ get() {{ return 'application/json'; }} }},
  }};
}}

const consoleStub = {{ error() {{}}, warn() {{}}, log() {{}} }};
const navigatorStub = {{ sendBeacon() {{ return false; }} }};
const windowStub = {{
  location: {{
    pathname: '/',
    search: '',
    hash: '#/dashboard',
    href: 'http://localhost/#/dashboard',
  }},
  performance: {{ now() {{ now += 5; return now; }} }},
  fetch: nativeFetch,
  console: consoleStub,
  navigator: navigatorStub,
  addEventListener(type, fn) {{ listeners.window[type] = fn; }},
  onerror: null,
}};
const documentStub = {{
  addEventListener(type, fn) {{ listeners.document[type] = fn; }},
}};

const sandbox = {{
  window: windowStub,
  document: documentStub,
  console: consoleStub,
  navigator: navigatorStub,
  fetch: nativeFetch,
  setTimeout(fn) {{ fn(); return 1; }},
  clearTimeout() {{}},
  URL,
  Blob,
}};

vm.runInNewContext(code, sandbox, {{ filename: 'error-report.js' }});

(async () => {{
{extra_js}
}})().catch((err) => {{
  console.error(err && err.stack || err);
  process.exit(1);
}});
"""


def test_fetch_calls_are_logged_to_client_endpoint() -> None:
    result = _run_node(_browser_harness(
        """
await windowStub.fetch('/api/index', { method: 'GET' });
const ev = uploads[0].events[0];
process.stdout.write(JSON.stringify({ uploads, nativeCalls, ev }));
"""
    ))
    ev = result["ev"]
    assert ev["level"] == "info"
    assert ev["action"] == "fetch"
    assert ev["method"] == "GET"
    assert ev["status_code"] == 200
    assert ev["target"] == "/api/index"
    assert ev["path"] == "/#/dashboard"
    assert [c["input"] for c in result["nativeCalls"]] == ["/api/index", "/api/log/client"]


def test_logging_endpoint_fetch_does_not_recursively_log_itself() -> None:
    result = _run_node(_browser_harness(
        """
await windowStub.fetch('/api/log/client', { method: 'POST', body: '{}' });
process.stdout.write(JSON.stringify({ uploads, nativeCalls }));
"""
    ))
    assert result["uploads"] == []
    assert [c["input"] for c in result["nativeCalls"]] == ["/api/log/client"]


def test_click_actions_are_logged() -> None:
    result = _run_node(_browser_harness(
        """
const button = {
  tagName: 'BUTTON',
  textContent: 'Run notebook cell',
  innerText: 'Run notebook cell',
  getAttribute(name) {
    if (name === 'id') return 'runCell';
    if (name === 'data-act') return 'run';
    return null;
  },
  closest() { return this; },
};
listeners.document.click({ type: 'click', target: button });
const ev = uploads[0].events[0];
process.stdout.write(JSON.stringify({ uploads, ev }));
"""
    ))
    ev = result["ev"]
    assert ev["level"] == "info"
    assert ev["action"] == "click"
    assert ev["event_type"] == "click"
    assert "button" in ev["target"]
    assert "#runCell" in ev["target"]
    assert "[run]" in ev["target"]
    assert "Run notebook cell" in ev["target"]


def test_frontend_logger_loaded_by_all_html_entrypoints(client, monorepo: Path) -> None:
    script = '<script src="/static/js/lib/error-report.js"></script>'
    script_path = "/static/js/lib/error-report.js"
    alert_script = '<script src="/static/js/lib/log-alert.js" defer></script>'
    alert_path = "/static/js/lib/log-alert.js"
    root = Path(__file__).resolve().parents[2]
    index_html = (root / "core/src/core/templates/index.html").read_text()
    assert script_path in index_html
    assert script not in index_html
    assert alert_path in index_html
    assert script in (root / "core/src/core/templates/spa.html").read_text()
    assert alert_script in (root / "core/src/core/templates/spa.html").read_text()

    (monorepo / "content" / "sample.md").write_text("# sample\n", encoding="utf-8")
    r = client.get("/view", params={"path": "content/sample.md"})
    assert r.status_code == 200
    assert script in r.text


def test_logs_spa_route_and_nav_are_registered() -> None:
    root = Path(__file__).resolve().parents[2]
    app_js = (root / "core/src/core/static/js/app.js").read_text()
    spa_html = (root / "core/src/core/templates/spa.html").read_text()
    logs_js = (root / "core/src/core/static/js/views/logs.js").read_text()

    assert '#/logs' in spa_html
    assert './views/logs.js' in app_js
    assert 'api.logTail' in logs_js
    assert 'api.logFiles' in logs_js
    assert 'novalidate: "novalidate"' in logs_js
    assert 'inputmode: "numeric"' in logs_js
    assert 'step: "50"' not in logs_js


def test_embedded_logs_view_registered_in_main_shell() -> None:
    root = Path(__file__).resolve().parents[2]
    index_html = (root / "core/src/core/templates/index.html").read_text()
    lab_app = (root / "core/src/core/static/js/lab-app.js").read_text()

    assert "/static/js/lab-app.js" in index_html
    assert 'id="logsView"' in index_html
    assert 'class="logs-terminal"' in index_html
    assert 'data-file="errors.log"' in index_html
    assert 'data-file="backend.log"' in index_html
    assert 'data-file="frontend.log"' in index_html
    assert ">Backend<" in index_html
    assert ">Frontend<" in index_html
    assert "const LOGS_PROJECT_ID = '__logs__'" in lab_app
    assert "const LOGS_POLL_MS = 2000" in lab_app
    assert "function goToLogs" in lab_app
    assert "function initLogs" in lab_app
    assert "projTabsPseudoOpen" in lab_app
    assert "function projTabsSetPseudoOpen" in lab_app
    assert "/api/ui/pseudo-tabs" in lab_app
    assert "projTabsSetPseudoOpen(LOGS_PROJECT_ID, true)" in lab_app
    assert "await projTabsSetPseudoOpen(pid, false)" in lab_app
    assert "Logs is pinned in slot 1 whenever it is open, active or not." in lab_app
    assert "ordered.findIndex(t => t.id === LOGS_PROJECT_ID)" in lab_app
    assert "termOpenForLogs()" in lab_app
    assert "function termOpenForLogs" in lab_app
    assert "if (document.body.classList.contains('logs-active')) return LOGS_PROJECT_ID" in lab_app
    logs_resolver = "if (document.body.classList.contains('logs-active')) return LOGS_PROJECT_ID"
    project_resolver = "if (currentProject && currentProject.is_project) return currentProject.name"
    assert lab_app.index(logs_resolver) < lab_app.index(project_resolver)
    assert "_TERM_VIS_KEY_PREFIX + 'logs'" in lab_app
    assert "return 'logs'" in lab_app
    assert "function logsStartLive" in lab_app
    assert "function logsRefresh" in lab_app
    assert "'logs-active'" in lab_app
    assert "window.goToLogs = goToLogs" in lab_app


def test_log_alert_script_tracks_unseen_error_cursor() -> None:
    root = Path(__file__).resolve().parents[2]
    log_alert = (root / "core/src/core/static/js/lib/log-alert.js").read_text()

    assert "/api/log/error-state" in log_alert
    assert "lab.errorLog.seenCursor" in log_alert
    assert "has-unseen" in log_alert
    assert "/?view=logs&file=errors.log&tail=500" in log_alert
    assert "Logs: new" in log_alert
    assert "window.goToLogs" in log_alert
