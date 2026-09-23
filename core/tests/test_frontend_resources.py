"""Real-browser resource sorting, exact stop targets and polling lifecycle."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_resource_dialog_in_chrome(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    checks = r'''
const assert = (value, message) => { if (!value) throw Error(message); };
const until = async (fn) => {
  for (let i=0; i<200; i++) { if (fn()) return; await new Promise(r=>setTimeout(r,5)); }
  throw Error('Timed out');
};
const polls = new Map(), posts = [], timers = {set:window.setTimeout.bind(window), clear:window.clearTimeout.bind(window)};
let nextPoll = 1000000, gets = 0, permit = false, fail = false, release = null, defer = false;
window.setTimeout = (fn, ms) => { if(ms!==3000) return timers.set(fn,ms); const id=nextPoll++;polls.set(id,fn);return id; };
window.clearTimeout = id => { polls.delete(id);timers.clear(id); };
window.confirm = () => permit;
const sample = {
  sampled_at:Date.now()/1000,
  host:{cpu_percent:42.1,cpu_count:10,memory_used:12*2**30,memory_total:32*2**30,memory_percent:37.5,swap_used:0},
  processes:[
    {pid:101,created:11,name:'Python',kind:'Jupyter',scope:'analysis.ipynb',cpu_percent:15,memory_bytes:2**30},
    {pid:202,created:22,name:'rg <img src=x onerror=alert(1)>',kind:'Terminal',scope:'Lab search',cpu_percent:130,memory_bytes:2**20},
    {pid:303,created:33,name:'Lab',kind:'Lab',scope:'Server and scans',cpu_percent:5,memory_bytes:300*2**20,protected:'Lab server'},
  ],files:{paused:false,scans:[]},warnings:[],
};
window.fetch = async (url, options={}) => {
  if(options.method==='POST') {
    const body=JSON.parse(options.body);posts.push({url,body});
    if(url.endsWith('/scans'))sample.files.paused=body.paused;
    return {ok:true,json:async()=>({})};
  }
  gets++;
  if(defer) return await new Promise(resolve=>{release=resolve;});
  if(fail)throw Error('Temporary failure');
  return {ok:true,json:async()=>structuredClone(sample)};
};
(async()=>{
  await LabResources.open();
  const dialog=document.querySelector('.lab-resources');
  const button=text=>[...dialog.querySelectorAll('button')].find(b=>b.textContent===text);
  const first=()=>dialog.querySelector('tbody tr');
  assert(first().textContent.includes('PID 202'),'CPU sort');
  assert(!dialog.querySelector('img'),'process text escaped');
  assert(dialog.querySelectorAll('tbody button').length===4,'protected process has no stop');
  assert(polls.size===1,'one scheduled poll');
  const select=dialog.querySelector('select');select.value='memory_bytes';select.dispatchEvent(new Event('change'));
  assert(first().textContent.includes('PID 101'),'memory sort');
  first().querySelector('button').click();await new Promise(r=>setTimeout(r,5));
  assert(posts.length===0,'cancel does not stop');
  permit=true;first().querySelector('button').click();await until(()=>posts.length===1&&!button('Refresh').disabled);
  assert(posts[0].body.pid===101&&posts[0].body.created===11&&posts[0].body.action==='stop','exact stop identity');
  first().querySelectorAll('button')[1].click();await until(()=>posts.length===2&&!button('Refresh').disabled);
  assert(posts[1].body.action==='kill','explicit force action');
  button('Pause file scans').click();await until(()=>button('Resume file scans'));
  assert(posts[2].body.paused===true,'pause scans');
  button('Resume file scans').click();await until(()=>button('Pause file scans'));
  assert(posts[3].body.paused===false,'resume scans');
  fail=true;button('Refresh').click();await until(()=>dialog.textContent.includes('Temporary failure'));
  assert(dialog.textContent.includes('values may be stale'),'stale error visible');
  fail=false;button('Refresh').click();await until(()=>!dialog.textContent.includes('Temporary failure'));
  Object.defineProperty(document,'hidden',{configurable:true,value:true});
  document.dispatchEvent(new Event('visibilitychange'));
  assert(polls.size===0,'hidden page stops polling');
  Object.defineProperty(document,'hidden',{configurable:true,value:false});
  document.dispatchEvent(new Event('visibilitychange'));await until(()=>polls.size===1);
  defer=true;button('Refresh').click();await until(()=>release);
  dialog.close();await new Promise(r=>setTimeout(r,5));
  assert(polls.size===0,'close cancels polling');
  release({ok:true,json:async()=>({...sample,processes:[]})});await new Promise(r=>setTimeout(r,5));
  assert(dialog.querySelectorAll('tbody tr').length===3,'closed response ignored');
  defer=false;await LabResources.open();assert(polls.size===1,'reopen resumes exactly one poll');
  assert(gets>=5,'live refreshes');
  assert(dialog.getBoundingClientRect().left>10,'dialog stays centered under the shell reset');
  // Only the process table should scroll horizontally if needed.
  assert(dialog.scrollWidth<=dialog.clientWidth,'dialog has no horizontal overflow');
  document.getElementById('result').textContent='PASS: sorting, safe targets, confirmation, pause, retry and polling lifecycle';
})().catch(error=>{document.getElementById('result').textContent='FAIL: '+error.stack;});
'''
    page = ('<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;'
            '--bg-secondary:#161b22;--border:#30363d;--text-primary:#e6edf3;'
            '--text-secondary:#8b949e;--accent:#58a6ff;--red:#f85149}'
            '*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:#0d1117;color:#fff}</style>'
            '<link rel="stylesheet" href="/static/css/resources.css"><pre id="result">PENDING</pre>'
            '<script src="/static/js/lib/resources.js"></script><script>' + checks + '</script>')
    (tmp_path / 'resources.html').write_text(page)
    (tmp_path / 'static').symlink_to(STATIC, target_is_directory=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = tmp_path / 'chrome-profile'
    process = None
    try:
        process = subprocess.Popen([
            chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
            '--no-default-browser-check', '--disable-background-networking',
            '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([
            node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile),
            f'http://127.0.0.1:{server.server_port}/resources.html', str(tmp_path / 'rendered.html'),
            str(tmp_path / 'resources.png'),
        ], capture_output=True, text=True, timeout=20, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        rendered = (tmp_path / 'rendered.html').read_text()
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
    assert result and result[1].startswith('PASS:'), result[1] if result else rendered[-1000:]
