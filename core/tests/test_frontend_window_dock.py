"""Real browser trial lifecycle, with a fake native controller and a frame-blocking site."""
import functools
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

STATIC = Path(__file__).resolve().parents[1] / 'src/core/static'


def test_window_dock_browser_lifecycle(tmp_path):
    _run_browser(tmp_path, native=False)


@pytest.mark.skipif(os.environ.get('LAB_TEST_NATIVE_DOCK') != '1', reason='Opt-in live Mac test; requires Accessibility permission')
def test_window_dock_native_geometry(tmp_path):
    from core.window_dock import manage
    assert manage('b' * 32, 'status').get('trusted'), 'Enable Lab Window Dock in macOS Accessibility first'
    _run_browser(tmp_path, native=True)


def _run_browser(tmp_path, native):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    (tmp_path / 'static').symlink_to(STATIC, target_is_directory=True)
    (tmp_path / 'index.html').write_text('''<!doctype html><title>Lab trial fixture</title>
      <link rel="stylesheet" href="/static/css/window-dock.css">
      <textarea id="draft">Unsaved task draft</textarea><main id="host">Existing Lab content</main>
      <button id="trial" onclick="LabWindowDock.open(document.querySelector('#host'))">Trial</button>
      <script>window.LAB_NATIVE_BROWSER_REUSE=true</script><script src="/static/js/lib/window-dock.js"></script>''')
    (tmp_path / 'site.html').write_text('<!doctype html><title>Autonomous site</title><h1>External resource</h1>')
    calls, state = [], {'trusted': False, 'active': False}

    class Handler(SimpleHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(request)
            operation = request['operation']
            if native:
                from core.window_dock import manage
                payload = {key: request[key] for key in ('slot', 'visible') if key in request}
                if operation == 'attach':
                    payload.update(parentMarker='Lab dock parent ' + request['owner'], childMarker='Lab dock popup ' + request['owner'])
                result = manage(request['owner'], operation, **payload)
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(result).encode()); return
            if operation == 'permission':
                state['trusted'] = True
            if operation == 'attach':
                state['active'] = True
            if operation in {'detach', 'close'}:
                state['active'] = False
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'ok': True, **state, 'detail': operation}).encode())

        def end_headers(self):
            if self.path.startswith('/site.html'):
                self.send_header('X-Frame-Options', 'DENY')
                self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            super().end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(tmp_path)))
    Thread(target=server.serve_forever, daemon=True).start()
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([chrome, *([] if native else ['--headless=new']), '--no-first-run', '--no-default-browser-check',
                                '--remote-debugging-port=0', '--user-data-dir=' + str(profile), 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const port=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n')[0];
 const base=`http://127.0.0.1:${port}`;
 const target=await fetch(base+'/json/new?about:blank',{method:'PUT'}).then(r=>r.json());
 async function connect(target){
  const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0;
  ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
  await new Promise(r=>ws.addEventListener('open',r,{once:true}));
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser failure');return r.result.value};
  return{send,evaluate,ws};
 }
 const {send,evaluate,ws}=await connect(target);
 async function wait(expression){for(let n=0;n<200;n++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,25))}throw Error('Timed out: '+expression)}
 async function click(selector){const p=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,...p,button:'left',clickCount:1})}
 const native=process.argv[3]==='native';
 if(!native)await send('Emulation.setDeviceMetricsOverride',{width:1400,height:950,deviceScaleFactor:1,mobile:false});
 else {const w=await send('Browser.getWindowForTarget',{targetId:target.id});await send('Browser.setWindowBounds',{windowId:w.windowId,bounds:{left:50,top:60,width:1100,height:800}})}
 await send('Page.navigate',{url:process.argv[2]+'/index.html'});await wait('!!window.LabWindowDock');
 await click('#trial');await wait(`!document.querySelector('[data-dock-status]').textContent.includes('Checking')`);
 if(!native){assert(await evaluate(`document.querySelector('[data-dock-start]').disabled`),'permission gates docking');await click('[data-dock-permission]')}
 await wait(`!document.querySelector('[data-dock-start]').disabled`);
 await evaluate(`document.querySelector('[data-dock-url]').value=${JSON.stringify(process.argv[2]+'/site.html?exact=1#section')}`);
 await click('[data-dock-start]');await wait(`document.querySelector('[data-dock-status]').textContent.startsWith('Docked.')`);
 assert(await evaluate(`document.title==='Lab trial fixture'&&document.querySelector('#draft').value==='Unsaved task draft'&&!document.querySelector('iframe')`),'draft/title retained and no iframe');
 assert(await evaluate(`document.querySelector('[data-dock-start]').disabled&&!document.querySelector('[data-dock-detach]').disabled`),'one active popup');
 let popup;
 for(let n=0;n<100;n++){popup=(await fetch(base+'/json/list').then(r=>r.json())).find(t=>t.url.includes('/site.html'));if(popup)break;await new Promise(r=>setTimeout(r,25))}
 assert(popup?.url.endsWith('?exact=1#section'),'exact external destination loaded');
 const other=await connect(popup);
 assert(await other.evaluate(`document.querySelector('h1').textContent==='External resource'&&window.opener===null&&document.referrer===''`),'top-level blocked site with no opener/referrer');
 if(native){
  await wait(`!!document.querySelector('.lab-window-dock').dataset.geometry`);
  const geometry=()=>evaluate(`JSON.parse(document.querySelector('.lab-window-dock').dataset.geometry)`);
  const before=await geometry(),windowInfo=await send('Browser.getWindowForTarget',{targetId:target.id});
  await send('Browser.setWindowBounds',{windowId:windowInfo.windowId,bounds:{left:90,top:90,width:1000,height:720}});
  await wait(`(()=>{const g=JSON.parse(document.querySelector('.lab-window-dock').dataset.geometry);return g.parent[2]<${before.parent[2]}&&g.popup.every((n,i)=>Math.abs(n-g.target[i])<=3)})()`);
  const after=await geometry();
  assert(after.popup[0]!==before.popup[0]&&after.popup[2]<before.popup[2],'native popup follows parent move and resize');
  console.log(JSON.stringify({nativeBefore:before,nativeAfter:after}));
 }
 await click('[data-dock-detach]');await wait(`!document.querySelector('[data-dock-start]').disabled`);
 assert((await fetch(base+'/json/list').then(r=>r.json())).some(t=>t.id===popup.id),'Detach keeps the external site open');
 await click('[data-dock-dismiss]');assert(await evaluate(`!document.querySelector('.lab-window-dock')&&document.querySelector('#draft').value==='Unsaved task draft'`),'exit preserves original content');
 other.ws.close();ws.close();
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''
    try:
        deadline = time.monotonic() + 12
        while not (profile / 'DevToolsActivePort').exists():
            assert time.monotonic() < deadline, 'Chrome startup timed out'
            time.sleep(.05)
        result = subprocess.run(['node', '-e', driver, str(profile), f'http://127.0.0.1:{server.server_port}', 'native' if native else 'fake'],
                                text=True, capture_output=True, timeout=50)
        assert result.returncode == 0, result.stdout + result.stderr
        if native:
            print(result.stdout)
        assert [c['operation'] for c in calls].count('attach') == 1
        assert any(c['operation'] == 'detach' for c in calls)
        assert len({c['owner'] for c in calls}) == 1
    finally:
        if native:
            from core.window_dock import manage
            for owner in {call['owner'] for call in calls}:
                manage(owner, 'detach')
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
        server.shutdown(); server.server_close()
