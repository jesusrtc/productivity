"""Resource links open real, isolated windows without replacing Lab content."""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import time
from threading import Thread

import pytest

from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


@pytest.mark.parametrize('viewport,collapsed,coop', [(1440, False, False), (1440, True, False), (390, True, False), (1440, False, True)])
def test_external_resource_popout_browser(client, owned_tasks, tmp_path, viewport, collapsed, coop):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    root, note, *_ = owned_tasks
    path = note.relative_to(root).as_posix()
    details = {}

    def visit(row):
        details[row['path']] = client.get('/api/assistant/note', params={'path':row['path']}).json()
        for child in row['children']:
            visit(child)

    detail = client.get('/api/assistant/note', params={'path':path}).json()
    visit(detail['tree'])
    fixture = {'index':client.get('/api/assistant').json(), 'details':details, 'path':path,
               'link':{'assistant_root':str(root), 'document_id':note.stem, 'path':path,
                       'title':'Weekly product review'}, 'collapsed':collapsed, 'coop':coop}
    # X-Frame-Options blocks embedding but permits this top-level resource.
    (tmp_path/'embedded.html').write_text('<!doctype html><title>Team dashboard</title><h1 id="resource-content">Team dashboard</h1>')
    (tmp_path/'static').symlink_to(STATIC, target_is_directory=True)
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/start'):
                self.send_response(302)
                self.send_header('Location', '/embedded.html?redirected=1#destination')
                self.end_headers()
            else:
                super().do_GET()

        def end_headers(self):
            self.send_header('X-Frame-Options', 'DENY')
            if coop:
                self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            super().end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture['url'] = f'http://localhost:{server.server_port}/embedded.html?org=1&theme=dark#dashboard'
    fixture['finalUrl'] = fixture['url']
    if coop:
        fixture['url'] = f'http://localhost:{server.server_port}/start?org=1#source'
        fixture['finalUrl'] = f'http://localhost:{server.server_port}/embedded.html?redirected=1#destination'
    setup = r'''
window.assert=(ok,message)=>{if(!ok)throw Error(message)};
window.until=async fn=>{for(let i=0;i<400;i++){if(fn())return;await new Promise(r=>setTimeout(r,10))}throw Error('Timed out: '+fn)};
let activeRoot='/trees/topic';
const calls=[];
window.LAB_EXTERNAL_BROWSER=true;
window.LAB_NATIVE_BROWSER_REUSE=true;
window.LabTaskTerminalBridge={cancelNavigation:()=>{throw Error('Pop-outs must not cancel Lab navigation')}};
const external={id:'google',kind:'external',url:FIX.url,label:'Team dashboard',type:'grafana'};
window.fetch=async(url,options={})=>{
 const u=new URL(url,location.href),body=options.body?JSON.parse(options.body):null;
 calls.push({path:u.pathname,method:options.method||'GET',body});let data;
 if(u.pathname==='/api/scope-links')data={links:[{...FIX.link,id:'doc',kind:'internal'},external],types:[],revision:'v1'};
 else if(u.pathname==='/api/assistant')data=FIX.index;
 else if(u.pathname==='/api/assistant/note')data=FIX.details[u.searchParams.get('path')];
 else if(u.pathname==='/api/assistant/content')return {ok:false,json:async()=>({detail:'Offline — keep the draft'})};
 else throw Error('Unexpected request '+url);
 return {ok:!!data,json:async()=>structuredClone(data)};
};
window.Terminal=class{constructor(){throw Error('Resource link must not create a terminal')}};
window.WebSocket=class{constructor(){throw Error('Resource link must not reconnect a terminal')}};
'''
    checks = r'''
window.prepare=async()=>{
 const links=document.querySelector('[data-scope-links]');
 await LabScopeLinks.mount(links,()=>activeRoot==='/trees/topic');
 document.getElementById('localDraft').value='Unsent file changes';
 document.getElementById('terminalDraft').value='Unsent terminal command';
 await AssistantView.openLinkedTask(FIX.link,{wholeDocument:true,inline:true});
 document.getElementById('assistantEditNote').click();
 await until(()=>document.querySelector('.assistant-note-editor textarea'));
 const draft=document.querySelector('.assistant-note-editor textarea');
 draft.value='Keep unsaved document draft';draft.dispatchEvent(new Event('input',{bubbles:true}));
 window.originalDraft=draft;window.originalGuard=AssistantView.navigationGuard();window.originalCalls=calls.length;
 assert(links.querySelector('[data-scope-link="1"]').title.startsWith('Opens in a pop-out over Lab'),'destination hint');
};
window.verify=()=>{
 assert(originalGuard(),'pop-out preserves pending document navigation');
 assert(originalDraft.isConnected&&originalDraft.value==='Keep unsaved document draft','pop-out retains editor and draft');
 assert(calls.length===originalCalls,'pop-out never saves or calls native window management');
 assert(!document.querySelector('dialog'),'pop-out never requires confirmation');
 assert(document.getElementById('localDraft').value==='Unsent file changes'&&document.getElementById('terminalDraft').value==='Unsent terminal command','existing drafts retained');
 assert(!document.querySelector('.workspace-external-host')&&!document.body.classList.contains('workspace-external-link'),'resource never creates an embedded view');
};
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'js/views/assistant.js', 'js/views/assistant-tasks.js',
        'js/lib/external-links.js', 'js/lib/scope-links.js'])
    page = tmp_path/'external-view.html'
    classes = 'workspace-active has-repo-tabs term-open' + (' sidebar-collapsed' if collapsed else '') + (' term-collapsed' if viewport < 760 else '')
    page.write_text('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css"><style>'+(STATIC/'css/assistant-tasks.css').read_text()+(STATIC/'css/workspace-documents.css').read_text()+'</style>'
        '<body class="'+classes+'" style="--sidebar-width:300px;--term-width:400px"><div class="topbar">Lab</div><div id="repoTabs"></div><div class="layout"><aside id="sidebar" class="sidebar"><section class="sidebar-scope-links" data-scope-links="/trees/topic"></section></aside><main id="content" class="main"><textarea id="localDraft"></textarea></main></div><aside id="termPanel" class="term-panel"><h3>Existing workspace terminal</h3><textarea id="terminalDraft"></textarea></aside><pre id="result" style="position:fixed;bottom:0;left:0;z-index:1000;font-size:8px">PENDING</pre>'
        '<script>const FIX='+json.dumps(fixture).replace('</',r'<\/')+';window.LAB_LINK_SERVICES='+(STATIC/'link-services.json').read_text()+';</script><script>'+setup+'</script>'+scripts+'<script>'+checks+'</script>')
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--user-data-dir='+str(profile), '--remote-debugging-port=0', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const base=`http://127.0.0.1:${port}`;
 const target=await fetch(base+'/json/new?about:blank',{method:'PUT'}).then(r=>r.json());
 async function connect(url){
  const ws=new WebSocket(url),pending=new Map();let sequence=0;
  ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
  await new Promise(r=>ws.addEventListener('open',r,{once:true}));
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value};
  return {ws,send,evaluate};
 }
 const parent=await connect(target.webSocketDebuggerUrl);
 await parent.send('Page.enable');
 await parent.send('Emulation.setDeviceMetricsOverride',{width:Number(process.argv[3]),height:1000,deviceScaleFactor:1,mobile:false});
 await parent.send('Page.navigate',{url:process.argv[2]});
 const until=async fn=>{for(let i=0;i<400;i++){const value=await fn();if(value)return value;await new Promise(r=>setTimeout(r,10))}throw Error('Timed out: '+fn)};
 await until(()=>parent.evaluate('typeof prepare==="function"'));
 await parent.evaluate('prepare()');
 const url=await parent.evaluate('FIX.url');
 const finalUrl=await parent.evaluate('FIX.finalUrl');
 const parentWindow=await parent.send('Browser.getWindowForTarget',{targetId:target.id});
 const click=async(modifiers=0)=>{
  const point=await parent.evaluate(`(()=>{document.body.classList.remove('sidebar-collapsed');const n=document.querySelector('[data-scope-link="1"]');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  for(const type of ['mousePressed','mouseReleased'])await parent.send('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1,modifiers});
 };
 const resourceTarget=async()=>{
  const result=await parent.send('Target.getTargets');
  return result.targetInfos.find(t=>t.type==='page'&&t.url===finalUrl);
 };
 await click();
 const popup=await until(resourceTarget),windowInfo=await parent.send('Browser.getWindowForTarget',{targetId:popup.targetId});
 assert(windowInfo.windowId!==parentWindow.windowId,'ordinary resource click opens a separate window');
 const list=await fetch(base+'/json/list').then(r=>r.json()),resource=await connect(list.find(t=>t.id===popup.targetId).webSocketDebuggerUrl);
 await until(()=>resource.evaluate('!!document.getElementById("resource-content")'));
 assert(await resource.evaluate('opener===null'),'resource cannot access Lab through an opener');
 assert(await resource.evaluate('document.referrer===""'),'resource receives no Lab referrer');
 await resource.evaluate('document.getElementById("resource-content").textContent="Retained resource state"');
 const popups=[{targetId:popup.targetId,...windowInfo}];
 for(let i=1;i<6;i++) {
  await click();
  const next=await until(async()=> (await parent.send('Target.getTargets')).targetInfos.find(
   t=>t.type==='page'&&t.url===finalUrl&&!popups.some(p=>p.targetId===t.targetId)));
  const info=await parent.send('Browser.getWindowForTarget',{targetId:next.targetId});
  assert(!popups.some(p=>p.windowId===info.windowId),'every repeated resource click creates a separate window');
  popups.push({targetId:next.targetId,...info});
 }
 assert(await resource.evaluate('document.getElementById("resource-content").textContent==="Retained resource state"'),'opening another resource preserves existing resource content');
 assert(windowInfo.bounds.width>=parentWindow.bounds.width-50,'resource is almost full Lab width');
 assert(windowInfo.bounds.top>=parentWindow.bounds.top+92,'first resource starts at the previous second cascade height');
 assert(windowInfo.bounds.left===parentWindow.bounds.left+24,'first resource starts at the previous second cascade horizontal position');
 assert(popups[1].bounds.top-windowInfo.bounds.top===36,'next resource exposes previous title bar');
 assert(popups[1].bounds.left-windowInfo.bounds.left===12,'resource windows cascade horizontally');
 assert(new Set(popups.slice(0,3).map(p=>`${p.bounds.left},${p.bounds.top}`)).size===3,'first three windows have distinct cascade positions');
 for(let i=0;i<3;i++)assert(JSON.stringify(popups[i+3].bounds)===JSON.stringify(popups[i].bounds),'each position repeats after three windows with the same size');
 for(const extra of popups.slice(1))await parent.send('Target.closeTarget',{targetId:extra.targetId});
 await parent.evaluate('verify();LabScopeLinks.closeExternal()');
 assert(await resourceTarget(),'Lab navigation leaves the independent resource window open');
 await parent.send('Target.closeTarget',{targetId:popup.targetId});resource.ws.close();
 await until(async()=>!await resourceTarget());
 await click(4); // macOS Command-click keeps the explicit normal browser tab.
 const tab=await until(resourceTarget),tabWindow=await parent.send('Browser.getWindowForTarget',{targetId:tab.targetId});
 assert(tabWindow.windowId===parentWindow.windowId,'modified click retains normal tab behavior');
 await parent.send('Target.closeTarget',{targetId:tab.targetId});
 await parent.evaluate(`(async()=>{verify();assert(await LabScopeLinks.openExternal({...external,url:'javascript:alert(1)'},activeRoot)===false,'unsafe URL rejected');assert(await LabScopeLinks.openExternal(external,activeRoot,{isCurrent:()=>false})===false,'retired links cannot open');})()`);
 parent.ws.close();console.log('PASS');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
        result = subprocess.run([node, '-e', driver, str(profile),
                                 f'http://127.0.0.1:{server.server_port}/{page.name}', str(viewport)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
