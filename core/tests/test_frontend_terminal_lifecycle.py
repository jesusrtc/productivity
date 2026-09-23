"""Startup ordering and real xterm disposal regressions."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'
APP = STATIC / 'js/lab-app.js'


def test_late_loaded_home_starts_after_terminal_state():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required')
    source = APP.read_text()
    # Keep the production order: a late-loaded script runs afterPageQuiet inline.
    blocks = [
        ('  let termXterm = null;', '  function _termActiveWorkspaceId()'),
        ('  afterPageQuiet(loadRepos);', '  // Auto-refresh workspace view'),
    ]
    chunks = []
    for start, end in blocks:
        offset = source.index(start)
        stop = source.find(end, offset)
        if stop < 0 and start == '  afterPageQuiet(loadRepos);':
            stop = source.find('  // Workspace and default-Home startup', offset)
        chunks.append((offset, source[offset:stop if stop >= 0 else None]))
    prelude = '''
const location = {search: '?view=productivity'};
const UI_CHECK = true;
const afterPageQuiet = fn => fn();
const loadRepos = () => {}, vaultRefresh = () => {}, workspaceTabsRefresh = () => {};
function initSelf() {
  if (termCurrentWorkspaceId !== null || termCurrentSession !== null || _termCache.size) {
    throw new Error('incorrect initial terminal state');
  }
  console.log('Home terminal ready');
}
'''
    result = subprocess.run([node, '-e', prelude + '\n'.join(s for _, s in sorted(chunks))],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'Home terminal ready' in result.stdout


def test_disposed_xterm_ignores_queued_viewport_frames(tmp_path):
    source = APP.read_text()
    start = source.find('  function _termGuardViewportDisposal(')
    helper = source[start:source.index('  function termEnsureXterm()', start)] if start >= 0 else ''
    scripts = '<script>' + (STATIC / 'vendor/xterm@5.3.0/xterm.min.js').read_text() + '</script>'
    checks = '''
const errors = [];
window.addEventListener('error', e => errors.push(e.message));
(async () => {
  for (let i = 0; i < 8; i++) {
    const host = document.createElement('div');
    host.style.cssText = 'width:800px;height:400px';
    document.body.appendChild(host);
    const xt = new Terminal();
    if (typeof _termGuardViewportDisposal === 'function') _termGuardViewportDisposal(xt);
    xt.open(host);
    await new Promise(resolve => requestAnimationFrame(resolve));
    // Queue both the refresh frame and reset's untracked syncScrollArea frame,
    // then remove the pane before either callback runs (rapid terminal switching).
    xt._core.viewport._refresh(false);
    xt.reset();
    xt.dispose();
    host.remove();
    await new Promise(resolve => requestAnimationFrame(resolve));
  }
  await new Promise(resolve => setTimeout(resolve, 50));
  document.getElementById('result').textContent = errors.length ? 'FAIL: ' + errors.join('; ') : 'PASS';
})().catch(e => document.getElementById('result').textContent = 'FAIL: ' + e.stack);
'''
    _check_terminal_page(tmp_path, scripts, helper + checks)


def _check_terminal_page(tmp_path, scripts, checks):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    page = tmp_path / 'terminal-lifecycle.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'
                    + (STATIC / 'vendor/xterm@5.3.0/xterm.min.css').read_text()
                    + '</style><body><pre id="result">PENDING</pre>' + scripts
                    + '<script>' + checks + '</script>')
    profile = tmp_path / 'chrome-profile'
    process = subprocess.Popen([
        chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
        '--no-default-browser-check', '--allow-file-access-from-files',
        '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(0.05)
        result = subprocess.run([
            node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile),
            page.as_uri(), str(tmp_path / 'rendered.html'),
        ], capture_output=True, text=True, timeout=20,
            env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        rendered = (tmp_path / 'rendered.html').read_text()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', rendered, re.S)
    assert result and result[1] == 'PASS', result[1] if result else rendered[-1000:]


def test_fresh_terminal_has_fitted_geometry_before_connection(tmp_path):
    source = APP.read_text()

    def section(start, end):
        offset = source.index(start)
        return source[offset:source.index(end, offset)]

    helpers = section('  function _termMakeContainer()', '  function _termClipboardImageFile')
    helpers += section('  function _termSetPaneActive(', '  // ─── Workspace tabs')
    helpers += section('  function _termGuardViewportDisposal(', '  function termEnsureXterm()')
    fresh = section('    const myContainer = _termMakeContainer();', '\n  function termSetStatus')
    # The extracted block ends with termAttach's closing brace.
    fresh = fresh.rsplit('  }', 1)[0]
    scripts = ''.join('<script>' + (STATIC / path).read_text() + '</script>' for path in (
        'vendor/xterm@5.3.0/xterm.min.js',
        'vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js',
    ))
    checks = r'''
const errors=[];window.addEventListener('error',e=>errors.push(e.message));
const assert=(ok,label)=>{if(!ok)throw Error(label);};
const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
let termXterm,termFitAddon,termContainer,termWS=null;
const termCurrentSession='owned',termCurrentWorkspaceId='alpha';
let connections=0;
function _termEnableWebgl() {}
function termSendResize() {}
function _openWS() {
  const dims=termFitAddon.proposeDimensions();
  assert(dims&&dims.cols>2&&dims.rows>2,'connection must not wait for a font measurement frame');
  assert(termXterm.cols===dims.cols&&termXterm.rows===dims.rows,'initial grid must match fitted geometry');
  connections++;
}
function freshPane(name,workspaceId) {
''' + fresh + r'''
}
(async()=>{
  const body=document.createElement('div');body.id='termBody';document.body.appendChild(body);
  for(const [width,height] of [[800,400],[420,250],[1000,600]]) {
    body.style.cssText=`position:relative;width:${width}px;height:${height}px`;
    termXterm=new Terminal({fontSize:13,fontFamily:'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace'});
    _termGuardViewportDisposal(termXterm);
    termFitAddon=new FitAddon.FitAddon();termXterm.loadAddon(termFitAddon);
    freshPane('owned','alpha');
    await new Promise(resolve=>termXterm.write('ready 中 e\u0301',resolve));
    await frame();await frame();
    assert(termXterm.buffer.active.getLine(0).translateToString(true)==='ready 中 e\u0301','first output changed');
    assert(document.activeElement===termXterm.textarea,'active terminal did not receive focus');
    termXterm.dispose();termContainer.remove();
    await frame();await frame();
  }
  assert(connections===3,'initial connection count changed');assert(!errors.length,errors.join('; '));
  document.getElementById('result').textContent='PASS';
})().catch(e=>document.getElementById('result').textContent='FAIL: '+e.stack);
'''
    _check_terminal_page(tmp_path, scripts, helpers + checks)
