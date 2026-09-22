"""The sidebar template cache preserves DOM behavior and has hard memory bounds."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_sidebar_template_cache_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    source = (ROOT / 'core/src/core/static/js/lab-app.js').read_text()
    start = source.index('  const _sidebarMarkupCache =')
    helper = source[start:source.index('  // Re-renders just the workspace file sidebar', start)]
    checks = r'''
const assert = (value, message) => {if (!value) throw Error(message)};
try {
  const sidebar = document.getElementById('sidebar');
  const original = '<a class="sidebar-file" onclick="window.clicked=(window.clicked||0)+1">File</a><input value="original">';
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a');
  const template = _sidebarMarkupCache.get('a').template;
  sidebar.querySelector('a').classList.add('active');
  sidebar.querySelector('a').appendChild(document.createElement('span')).className='git-badge';
  sidebar.querySelector('input').value='edited';
  _replaceWorkspaceSidebarMarkup(sidebar, '<a>Different workspace</a>', 'b');
  _replaceWorkspaceSidebarMarkup(sidebar, original, 'a');
  assert(_sidebarMarkupCache.get('a').template === template, 'same markup reuses parsed template');
  assert(!sidebar.querySelector('.active,.git-badge'), 'live selection and decorations stay outside template');
  assert(sidebar.querySelector('input').value === 'original', 'live control state does not corrupt template');
  sidebar.querySelector('a').click();
  assert(window.clicked === 1, 'cloned inline file actions still run');
  _replaceWorkspaceSidebarMarkup(sidebar, original+'<a>New file</a>', 'a');
  assert(sidebar.querySelectorAll('a').length === 2, 'changed files appear');
  assert(_sidebarMarkupCache.get('a').template !== template, 'changed markup replaces template');
  for (let i=0;i<10;i++) _replaceWorkspaceSidebarMarkup(sidebar, '<a>'+i+'</a>', 'scope-'+i);
  assert(_sidebarMarkupCache.size === 4, 'workspace count bounded');
  assert([..._sidebarMarkupCache.keys()].join(',') === 'scope-6,scope-7,scope-8,scope-9', 'oldest scopes evicted');
  const many = '<i></i>'.repeat(20000);
  for (let i=0;i<4;i++) _replaceWorkspaceSidebarMarkup(sidebar, many, 'large-'+i);
  assert(_sidebarMarkupCacheElements === 60000 && _sidebarMarkupCache.size === 3, 'aggregate elements bounded');
  _replaceWorkspaceSidebarMarkup(sidebar, '<i></i>'.repeat(60001), 'huge');
  assert(sidebar.children.length === 60001, 'oversized tree remains complete');
  assert(!_sidebarMarkupCache.has('huge') && _sidebarMarkupCacheElements === 60000, 'oversized tree not retained');
  _replaceWorkspaceSidebarMarkup(sidebar, '<a>Small again</a>', 'large-3');
  assert(_sidebarMarkupCacheElements === 40001, 'replacement releases previous template accounting');
  document.getElementById('result').textContent='PASS';
} catch(error) {document.getElementById('result').textContent='FAIL: '+error.stack;}
'''
    page = tmp_path / 'sidebar-cache.html'
    page.write_text('<!doctype html><meta charset="utf-8"><body><pre id="result">PENDING</pre>'
                    '<aside id="sidebar"></aside><script>' + helper + checks + '</script>')
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([
        chrome, '--headless', '--no-sandbox', '--no-first-run', '--disable-background-networking',
        '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        rendered = tmp_path / 'rendered.html'
        result = subprocess.run([
            node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile), page.as_uri(), str(rendered),
        ], capture_output=True, text=True, timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        match = re.search(r'<pre id="result">(.*?)</pre>', rendered.read_text(), re.S)
        assert match and match[1] == 'PASS', match[1] if match else 'No browser result'
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
