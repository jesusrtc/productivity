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
    root = Path(__file__).resolve().parents[2]
    assert script in (root / "core/src/core/templates/index.html").read_text()
    assert script in (root / "core/src/core/templates/spa.html").read_text()

    (monorepo / "content" / "sample.md").write_text("# sample\n", encoding="utf-8")
    r = client.get("/view", params={"path": "content/sample.md"})
    assert r.status_code == 200
    assert script in r.text
