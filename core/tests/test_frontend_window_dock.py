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


def test_asset_auto_docking_and_fallbacks(tmp_path):
    _run_browser(tmp_path, native=False, automatic=True)


def _run_browser(tmp_path, native, automatic=False):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    (tmp_path / 'static').symlink_to(STATIC, target_is_directory=True)
    (tmp_path / 'index.html').write_text('''<!doctype html><title>Lab trial fixture</title>
      <link rel="stylesheet" href="/static/css/window-dock.css">
      <textarea id="draft">Unsaved task draft</textarea><main id="host">Existing Lab content</main>
      <button id="trial" onclick="LabWindowDock.open(document.querySelector('#host'))">Trial</button>
      <script>window.LAB_NATIVE_BROWSER_REUSE=true</script><script src="/static/js/lib/window-dock.js"></script>''')
    if automatic:
        objective_js = (STATIC / 'js/lib/workspace-objectives.js').read_text()
        open_link = objective_js[objective_js.index('  function openLinkUrl('):objective_js.index('  function linkPropertiesHtml(')]
        (tmp_path / 'index.html').write_text('''<!doctype html><title>Lab trial fixture</title>
          <link rel="stylesheet" href="/static/css/lab-shell.css"><link rel="stylesheet" href="/static/css/window-dock.css">
          <link rel="stylesheet" href="/static/css/settings-center.css">
          <body class="term-open" style="--sidebar-width:230px;--term-width:300px">
          <div class="topbar">Lab</div><div class="layout"><aside id="sidebar" class="sidebar">
          <button id="asset" onclick="LabScopeLinks.openExternal({url:site()},'/scope')">Scope asset</button>
          <button id="objective" onclick="openLinkUrl(site(),event)">Objective asset</button></aside>
          <main id="content" class="main"><textarea id="draft">Unsaved task draft</textarea><p>Working document</p></main></div>
          <aside id="termPanel" class="term-panel"><textarea id="terminalDraft">Unsent command</textarea></aside>
          <script>
          window.LAB_NATIVE_BROWSER_REUSE=true;window.LAB_IS_ADMIN=true;
          window.LabSettingsBridge={initialScopes:()=>[]};
          let sequence=0;const site=()=>location.origin+'/site.html?exact='+(++sequence)+'#section';
          const validLinkUrl=()=>true,notify=message=>{throw Error(message)};
          window.mode='permission';window.dockCalls=[];const realFetch=fetch;
          window.fetch=async(url,options={})=>{
            if(url==='/api/ui/window-dock'){
              const req=JSON.parse(options.body);dockCalls.push(req);
              const mode=window.mode;
              if(req.operation==='permission')window.mode='ready';
              if(mode==='slow-status'&&req.operation==='status')await new Promise(r=>window.releaseStatus=r);
              if(mode==='slow-attach'&&req.operation==='attach')await new Promise(r=>window.releaseAttach=r);
              const error=mode==='permission'&&req.operation==='status'||mode==='attach-error'&&req.operation==='attach'||mode==='offline'&&req.operation==='update'||mode==='close-error'&&req.operation==='close';
              const data={ok:!error,trusted:!error,active:!error&&['attach','update'].includes(req.operation),detail:error?(mode==='permission'?'Enable Lab Window Dock in System Settings → Privacy & Security → Accessibility.':'Window helper unavailable; check setup.'):'Ready to dock a Chrome window.'};
              return {ok:true,json:async()=>data};
            }
            if(url==='/api/settings/global'||url==='/api/agents/available')return{ok:true,json:async()=>({})};
            if(url==='/api/vaults/workspaces')return{ok:true,json:async()=>({vaults:[]})};
            return realFetch(url,options);
          };
          </script><script>''' + open_link + '''</script>
          <script src="/static/js/lib/window-dock.js"></script><script src="/static/js/lib/external-links.js"></script>
          <script src="/static/js/lib/scope-links.js"></script><script src="/static/js/lib/settings-center.js"></script>''')
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

 if(process.argv[4]==='auto'){
  const q=selector=>`document.querySelector(${JSON.stringify(selector)})`;
  const alertText=()=>evaluate(`${q('.lab-dock-alert')}?.textContent||''`);
  const siteTargets=()=>fetch(base+'/json/list').then(r=>r.json()).then(rows=>rows.filter(t=>t.url.includes('/site.html')));
  async function siteOpened(){
   const sequence=await evaluate('sequence');let found;
   for(let n=0;n<150;n++){found=(await siteTargets()).find(t=>t.url.endsWith(`?exact=${sequence}#section`));if(found)break;await new Promise(r=>setTimeout(r,25))}
   assert(found,'requested external page loads exactly once');
   const page=await connect(found);for(let n=0;n<100&&!await page.evaluate(`!!document.querySelector('h1')`);n++)await new Promise(r=>setTimeout(r,25));assert(await page.evaluate(`window.opener===null&&document.referrer===''&&!!document.querySelector('h1')`),'autonomous framing-blocked page has no opener or referrer');page.ws.close();
   assert((await siteTargets()).filter(t=>t.url===found.url).length===1,'no duplicate fallback popup');return found;
  }
  async function dismiss(){await click('[data-dock-alert-dismiss]');assert(await evaluate(`!${q('.lab-dock-alert')}`),'alert dismisses')}
  const retained=()=>evaluate(`document.querySelector('#draft').value==='Unsaved task draft'&&document.querySelector('#terminalDraft').value==='Unsent command'&&document.title==='Lab trial fixture'&&!document.querySelector('iframe')`);
  await click('#asset');await wait(`!!${q('.lab-dock-alert')}`);await siteOpened();
  assert((await alertText()).includes('Accessibility'),'missing permission explains configuration');
  assert(await retained(),'permission fallback retains drafts, title and main view');
  assert(await evaluate(`!${q('.lab-window-dock')}`),'failed dock removes reservation');
  await click('[data-dock-settings]');await wait(`!!${q('[data-dock-auto]')}`);
  assert(await evaluate(`${q('[data-dock-auto]')}.checked`),'asset auto docking defaults on');
  await wait(`!${q('#labSettingsCenter [data-dock-permission]')}.disabled`);
  await click('#labSettingsCenter [data-dock-permission]');await wait(`mode==='ready'&&!${q('#labSettingsCenter [data-dock-check]')}.disabled`);
  await click('[data-dock-auto]');assert(await evaluate(`localStorage.getItem('labAutoDockAssets-v1')==='false'`),'disable persists per browser');
  await click('#labSettingsCenter [data-close]');await dismiss();
  const disabledCalls=await evaluate('dockCalls.length');await click('#asset');await siteOpened();
  assert(await evaluate(`dockCalls.length===${disabledCalls}&&!${q('.lab-dock-alert')}`),'disabled preference uses ordinary popup without native requests or warnings');
  await evaluate(`localStorage.setItem('labAutoDockAssets-v1','true')`);
  await click('#objective');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  assert(await retained(),'automatic docking preserves mounted drafts and title');
  assert(await evaluate(`(()=>{const a=${q('.lab-window-dock')}.getBoundingClientRect(),c=${q('#content')}.getBoundingClientRect(),slot=${q('[data-dock-slot]')}.getBoundingClientRect();return Math.abs(a.left-c.left)<1&&Math.abs(a.right-c.right)<1&&a.top>=88&&slot.bottom<innerHeight})()`),'dock occupies only central column, below header');
  const oldSlot=await evaluate(`dockCalls.filter(c=>c.operation==='update').at(-1).slot`);
  await evaluate(`document.body.style.setProperty('--term-width','400px')`);
  await wait(`dockCalls.filter(c=>c.operation==='update').at(-1).slot[2]<${oldSlot[2]}-.05`);
  await evaluate(`LabSettings.open({section:'docking'})`);await wait(`dockCalls.filter(c=>c.operation==='update').at(-1).visible===false`);
  await click('#labSettingsCenter [data-close]');
  const oldOwner=await evaluate(`dockCalls.findLast(c=>c.operation==='attach').owner`);
  await click('#asset');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  assert(await evaluate(`dockCalls.some(c=>c.owner==='${oldOwner}'&&c.operation==='detach')`),'opening another asset releases only the old controller');
  assert(await evaluate(`document.querySelectorAll('.lab-window-dock').length===1`),'one panel per view');
  const beforeDetach=(await siteTargets()).length;
  await click('[data-dock-detach]');assert(await evaluate(`!${q('.lab-window-dock')}`),'Detach restores central work area');
  assert((await siteTargets()).length===beforeDetach,'Detach preserves open sites');
  await click('#asset');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  await evaluate(`window.mode='close-error'`);await click('[data-dock-close]');await wait(`!!${q('.lab-dock-alert')}`);
  assert((await alertText()).includes('helper unavailable'),'failed native Close keeps the site and reports the error');await dismiss();
  await evaluate(`window.mode='attach-error'`);await click('#asset');await wait(`!!${q('.lab-dock-alert')}`);await siteOpened();
  assert((await alertText()).includes('helper unavailable'),'attach errors explain fallback');await dismiss();
  await evaluate(`window.mode='slow-status'`);await click('#asset');
  // Wait longer than the actual eight-second UI deadline, not a shortened test-only timeout.
  for(let n=0;n<100&&!await evaluate(`!!${q('.lab-dock-alert')}`);n++)await new Promise(r=>setTimeout(r,100));
  assert((await alertText()).includes('took too long'),'slow setup falls back promptly');await siteOpened();
  const slowOwner=await evaluate(`dockCalls.findLast(c=>c.operation==='status').owner`);
  await evaluate('releaseStatus()');await new Promise(r=>setTimeout(r,100));
  assert(await evaluate(`!dockCalls.some(c=>c.owner==='${slowOwner}'&&c.operation==='attach')`),'late setup cannot attach after fallback');await dismiss();
  await evaluate(`window.mode='slow-attach'`);await click('#asset');await wait('!!window.releaseAttach');
  const pendingOwner=await evaluate(`dockCalls.findLast(c=>c.operation==='attach').owner`);
  await evaluate(`window.mode='ready'`);await click('#objective');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  await evaluate('releaseAttach()');await wait(`dockCalls.filter(c=>c.owner==='${pendingOwner}'&&c.operation==='detach').length>=2`);
  assert(await evaluate(`${q('[data-dock-status]')}.textContent.startsWith('Docked.')&&document.querySelectorAll('.lab-window-dock').length===1`),'stale attach cleanup does not touch the new dock');
  await evaluate(`LabScopeLinks.closeExternal()`);assert(await evaluate(`!${q('.lab-window-dock')}`),'navigation hook releases alignment');
  await click('#asset');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  await evaluate(`document.querySelector('#content').append(document.createElement('section'))`);
  await wait(`!${q('.lab-window-dock')}`);assert(await retained(),'central navigation releases alignment without losing drafts');
  await click('#asset');await wait(`${q('[data-dock-status]')}?.textContent.startsWith('Docked.')`);await siteOpened();
  await evaluate(`window.mode='offline'`);await wait(`!!${q('.lab-dock-alert')}`);assert((await alertText()).includes('helper unavailable'),'heartbeat failure detaches and alerts');await dismiss();
  await evaluate(`window.mode='ready';window.realOpen=window.open;window.open=()=>null`);await click('#asset');await wait(`!!${q('.lab-dock-alert')}`);
  assert((await alertText()).includes('Allow pop-ups')&&await evaluate(`!!${q('.lab-dock-alert a[target="_blank"]')}`),'blocked popup provides direct retry and configuration');
  await evaluate(`window.open=window.realOpen`);await dismiss();
  await evaluate(`document.body.style.setProperty('--term-width','1000px')`);await click('#asset');await wait(`!!${q('.lab-dock-alert')}`);await siteOpened();
  assert((await alertText()).includes('Enlarge'),'small central area falls back');await dismiss();
  await evaluate(`window.LAB_NATIVE_BROWSER_REUSE=false`);const unsupportedCalls=await evaluate('dockCalls.length');
  await click('#asset');await wait(`!!${q('.lab-dock-alert')}`);await siteOpened();
  assert(await evaluate(`dockCalls.length===${unsupportedCalls}`),'unsupported client never contacts native helper');
  assert((await alertText()).includes('Mac running Lab'),'unsupported platform explains requirement');await dismiss();
  await evaluate(`window.LAB_NATIVE_BROWSER_REUSE=true;window.mode='permission';document.body.style.setProperty('--term-width','300px');const editor=document.createElement('dialog');editor.id='editor';editor.innerHTML='<button id="editorOpen" onclick="openLinkUrl(site(),event)">Open</button>';document.body.append(editor);editor.showModal()`);
  await click('#editorOpen');await wait(`!!${q('#editor .lab-dock-alert')}`);await siteOpened();
  await dismiss();await evaluate(`document.querySelector('#editor').close();document.querySelector('#editor').remove()`);
  const modifierCalls=await evaluate('dockCalls.length');
  await evaluate(`document.querySelector('#objective').dispatchEvent(new MouseEvent('click',{ctrlKey:true,bubbles:true}))`);await siteOpened();
  assert(await evaluate(`dockCalls.length===${modifierCalls}&&!${q('.lab-dock-alert')}`),'modified asset click keeps ordinary tab behavior');
  assert(await retained(),'all failure paths preserve Lab drafts and title');ws.close();return;
 }
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
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    try:
        deadline = time.monotonic() + 12
        while not (profile / 'DevToolsActivePort').exists():
            assert time.monotonic() < deadline, 'Chrome startup timed out'
            time.sleep(.05)
        result = subprocess.run(['node', '-e', driver, str(profile), f'http://127.0.0.1:{server.server_port}', 'native' if native else 'fake', 'auto' if automatic else 'manual'],
                                text=True, capture_output=True, timeout=50)
        assert result.returncode == 0, result.stdout + result.stderr
        if native:
            print(result.stdout)
        if not automatic:
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
