"""Render native notebook MIME in real Chrome using only Lab's local assets."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import threading
import time

import pytest

from core.diff_parser import parse_notebook_output

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "core/src/core/static"


def test_native_plotly_saved_live_and_duplicate_views(tmp_path):
    chrome = (os.environ.get("CHROME_BIN") or shutil.which("chromium")
              or shutil.which("google-chrome")
              or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    node = shutil.which("node")
    if not Path(chrome).is_file() or not node:
        pytest.skip("Chrome and Node are required for Plotly rendering checks")
    app = (STATIC / "js/lab-app.js").read_text()

    def between(start, end):
        return app[app.index(start):app.index(end, app.index(start))]

    helpers = "\n".join([
        between("  const _assetPromises =", "  function loadStyleOnce("),
        between("  function ensurePlotly()", "  function ensureMarked()"),
        between("  function _renderNbOutput(", "  function _renderNbExpandButton("),
        between("  function _waitForPlotly(", "  async function renderNotebookView("),
        between("  async function _handleNotebookExecutionEvent(", "  // WS live refresh"),
    ])
    figure = {
        "data": [{
            "type": "scatter", "mode": "lines+markers", "name": "Series",
            "x": {"dtype": "i4", "bdata": base64.b64encode(struct.pack("<3i", 1, 2, 3)).decode()},
            "y": {"dtype": "f8", "bdata": base64.b64encode(struct.pack("<3d", 2, 4, 3)).decode()},
        }],
        "layout": {"title": {"text": "Native Plotly"}, "height": 320, "showlegend": True},
        "config": {"scrollZoom": True, "displaylogo": False},
        "frames": [{"name": "next", "data": [{"y": [3, 2, 4]}]}],
    }
    output = parse_notebook_output({
        "output_type": "display_data",
        "data": {"application/vnd.plotly.v1+json": figure},
        "transient": {"display_id": "chart-1"},
    })
    checks = r'''
const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const escAttr = s => esc(s).replaceAll('"', '&quot;');
// Match the app's notebook AMD resolver without preloading Plotly.
window.require = (deps, callback) => callback(...deps.map(name => window.Plotly));
const _nbLivePaths = new Set();
const _nbLiveKey = (vault, path) => vault + path;
const _currentOpenNotebookRelPath = () => 'plotly.ipynb';
const _reconcileOpenNotebook = () => { throw new Error('unexpected reconciliation'); };
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const until = async (predicate, message) => {
  for (let i = 0; i < 150; i++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(message);
};
(async () => {
  const saved = document.getElementById('saved');
  saved.innerHTML = _renderNbOutput(OUTPUT) + _renderNbOutput(OUTPUT);
  assert(!window.Plotly, 'Plotly must load lazily');
  await activateNotebookScripts(saved);
  const charts = saved.querySelectorAll('.nb-plotly-chart');
  await until(() => [...charts].every(chart => chart._transitionData?._frames?.length === 1), 'both charts and frames render');
  assert(charts[0] !== charts[1], 'independent chart targets');
  for (const chart of charts) {
    assert(chart.querySelectorAll('.scatterlayer .point').length === 3, 'typed arrays draw three points');
    assert(chart._fullData[0].x[2] === 3 && chart._fullData[0].y[1] === 4, 'typed-array values preserved');
    assert(chart._context.scrollZoom && !chart._context.displaylogo, 'config preserved');
    assert(chart._fullLayout.height === 320, 'layout preserved');
  }
  Plotly.Fx.hover(charts[0], [{curveNumber: 0, pointNumber: 1}]);
  assert(charts[0].querySelector('.hoverlayer .hovertext'), 'hover is interactive');
  await Plotly.relayout(charts[0], {'xaxis.range': [1.2, 2.2]});
  const originalData = charts[0]._fullData;
  await activateNotebookScripts(saved);
  assert(charts[0]._fullData === originalData && charts[0].layout.xaxis.range[0] === 1.2, 'repeat activation preserves zoom');

  // Drive the actual live-output handler, including display_id replacement.
  const event = {path: 'plotly.ipynb', phase: 'output', cell_id: 'live-cell', sequence: 1, output: OUTPUT};
  await _handleNotebookExecutionEvent(event);
  const live = document.getElementById('live');
  await until(() => live.querySelectorAll('.scatterlayer .point').length === 3, 'live append renders');
  const oldChart = live.querySelector('.nb-plotly-chart');
  await _handleNotebookExecutionEvent({...event, sequence: 2, operation: 'replace'});
  await until(() => live.querySelectorAll('.scatterlayer .point').length === 3, 'live replacement renders');
  assert(live.querySelectorAll('.nb-plotly-chart').length === 1, 'display replacement does not append');
  assert(oldChart !== live.querySelector('.nb-plotly-chart'), 'updated display replaces old chart');

  const resources = performance.getEntriesByType('resource');
  assert(resources.some(r => r.name.includes('/static/vendor/plotly@3.5.1/')), 'uses vendored Plotly');
  assert(resources.every(r => new URL(r.name).origin === location.origin), 'no external requests');
  const broken = document.getElementById('broken');
  broken.innerHTML = _renderNbOutput(OUTPUT);
  const newPlot = Plotly.newPlot;
  Plotly.newPlot = () => Promise.reject(new Error('test render failure'));
  await activateNotebookScripts(broken);
  await until(() => broken.textContent.includes('Unable to render Plotly chart: test render failure'), 'failure is visible');
  Plotly.newPlot = newPlot;
  document.getElementById('result').textContent = 'PASS: saved, live, replacement, typed arrays, frames, hover, zoom, local loading and visible errors';
})().catch(error => { document.getElementById('result').textContent = 'FAIL: ' + error.stack; });
'''
    page = (
        '<!doctype html><meta charset="utf-8"><style>body{margin:20px}#saved{display:flex}'
        '#saved>.nb-output-html{width:50%}</style><body><div id="saved"></div>'
        '<div id="live" class="nb-cell-interactive" data-cell-id="live-cell" data-live-sequence="0">'
        '<div class="nb-outputs"><div class="nb-outputs-body"></div></div></div>'
        '<div id="broken"></div><pre id="result">PENDING</pre><script>'
        'const OUTPUT = ' + json.dumps(output).replace("<", "\\u003c") + ';\n'
        + helpers + checks + '</script>'
    )
    (tmp_path / "plotly.html").write_text(page)
    (tmp_path / "static").symlink_to(STATIC, target_is_directory=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / "chrome-profile"
    process = None
    try:
        process = subprocess.Popen([
            chrome, "--headless", "--disable-gpu", "--no-sandbox", "--no-first-run",
            "--no-default-browser-check", "--disable-background-networking",
            "--user-data-dir=" + str(profile), "--remote-debugging-port=0", "about:blank",
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic() + 10
        while not (profile / "DevToolsActivePort").exists():
            assert process.poll() is None and time.monotonic() < deadline, "Chrome did not start"
            time.sleep(0.05)
        result = subprocess.run([
            node, str(ROOT / "scripts/chrome-dump-auth.mjs"), str(profile),
            f"http://127.0.0.1:{server.server_port}/plotly.html", str(tmp_path / "rendered.html"),
            str(tmp_path / "plotly.png"),
        ], capture_output=True, text=True, timeout=20,
            env={**os.environ, "LAB_UI_AUTH_COOKIE": ""})
        assert result.returncode == 0, result.stderr
        rendered = (tmp_path / "rendered.html").read_text()
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', rendered, re.S)
    assert result and result[1].startswith("PASS:"), result[1] if result else rendered[-1000:]
