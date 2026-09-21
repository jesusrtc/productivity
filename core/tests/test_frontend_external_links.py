"""Real DOM checks for the shared external-link click policy."""
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import subprocess
import time
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_external_link_clicks_in_browser(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    source = (ROOT / 'core/src/core/static/js/lib/external-links.js').read_text()
    checks = r'''
const assert = (ok, message) => { if (!ok) throw new Error(message); };
const requests = [], tabs = [];
window.LAB_EXTERNAL_BROWSER = true;
window.fetch = async (url, options) => { requests.push({url, options}); return {ok:true}; };
window.open = (...args) => tabs.push(args);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const anchor = (href, doc = document) => {
  const a = doc.createElement('a'); a.href = href;
  a.innerHTML = '<span>Link</span>'; doc.body.append(a); return a;
};
const click = (link, options = {}) => {
  const event = new MouseEvent(options.button === 1 ? 'auxclick' : 'click',
    {bubbles:true, cancelable:true, button:0, ...options});
  link.firstChild.dispatchEvent(event); return event;
};
(async () => {
  for (const options of [{}, {metaKey:true}, {ctrlKey:true}, {shiftKey:true}, {button:1}]) {
    const a = anchor('https://example.com/article?x=1&y=2#part');
    a.onclick = () => { throw new Error('External link reached document handler'); };
    assert(click(a, options).defaultPrevented, 'external click is intercepted');
  }
  // Keyboard activation uses a click with button 0.
  anchor('https://example.com/keyboard').click();
  await tick();
  assert(requests.length === 6 && tabs.length === 0, 'one OS request per activation and no app windows');
  assert(requests[0].url === '/api/ui/open-external' && requests[0].options.method === 'POST', 'browser handoff endpoint');
  assert(JSON.parse(requests[0].options.body).url === 'https://example.com/article?x=1&y=2#part', 'URL preserved');
  for (const href of ['#heading', './document.md', location.origin + '/?view=assistant', 'mailto:test@example.com', 'javascript:void(0)', 'data:text/plain,hello']) {
    const link = anchor(href);
    let handled = false;
    link.addEventListener('click', event => { handled = true; event.preventDefault(); });
    click(link);
    assert(handled, 'internal links and other protocols retain their handlers');
  }
  const download = anchor('https://example.com/file'); download.download = 'file';
  let downloaded = false;
  download.addEventListener('click', event => { downloaded = true; event.preventDefault(); });
  click(download);
  assert(downloaded && requests.length === 6, 'downloads are not redirected');
  assert(!click(anchor('https://example.com'), {button:2}).defaultPrevented, 'right click remains available');

  // Dynamically loaded same-origin HTML previews get the same capture policy.
  const frame = document.createElement('iframe');
  const loaded = new Promise(resolve => frame.addEventListener('load', resolve, {once:true}));
  frame.srcdoc = '<body><p>Preview</p></body>'; document.body.append(frame); await loaded;
  click(anchor('https://example.com/preview', frame.contentDocument), {metaKey:true});
  await tick();
  assert(requests.length === 7, 'preview iframe links use the system browser');

  // Remote users open the link in their own browser instead of the host desktop.
  window.LAB_EXTERNAL_BROWSER = false;
  click(anchor('https://example.com/remote'));
  assert(tabs.length === 1 && tabs[0][1] === '_blank' && tabs[0][2].includes('noopener'), 'remote browser tab');
  assert(requests.length === 7, 'remote click never calls host opener');
  window.LAB_EXTERNAL_BROWSER = true;
  const associated = anchor('https://example.com/associated');
  associated.dataset.labClientExternal = '';
  click(associated);
  assert(tabs.length === 2 && requests.length === 7, 'associated documents stay on the client even with a loopback/server flag');
  assert(await LabExternalLinks.open('javascript:alert(1)') === false, 'terminal URLs are validated');

  window.fetch = async () => ({ok:false});
  click(anchor('https://example.com/failure')); await tick();
  const fallback = document.querySelector('dialog[open] a');
  assert(fallback && fallback.href === 'https://example.com/failure', 'failed launch offers a fresh browser click');
  let retried = false;
  fallback.addEventListener('click', event => { retried = true; event.preventDefault(); });
  fallback.click();
  assert(retried, 'fallback is not intercepted again');
  const closed = new Promise(resolve => document.querySelector('dialog').addEventListener('close', resolve, {once:true}));
  document.querySelector('dialog button').click(); await closed;
  assert(!document.querySelector('dialog'), 'fallback cleans up');
  document.getElementById('result').textContent = 'PASS';
})().catch(error => document.getElementById('result').textContent = 'FAIL: ' + error.stack);
'''
    page = tmp_path / 'external-links.html'
    page.write_text('<!doctype html><body><pre id="result">PENDING</pre><script>' + source + '</script><script>' + checks + '</script>')
    profile = tmp_path / 'chrome-profile'
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
                                '--no-default-browser-check', '--allow-file-access-from-files',
                                '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile),
                                 f'http://127.0.0.1:{server.server_port}/{page.name}', str(tmp_path / 'dom.html')], capture_output=True,
                                text=True, timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path / 'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
    assert result and result[1] == 'PASS', result[1] if result else html[-1000:]
