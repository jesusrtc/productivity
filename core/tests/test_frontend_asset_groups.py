"""Native pointer grouping, hover cancellation, ordering and exact link targets."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest
from lab import objectives

STATIC = Path(__file__).resolve().parents[1] / 'src/core/static'


def test_client_asset_group_flow(client, monorepo, seed_workspace, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    folder = seed_workspace()
    oid = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Document sections'})['objectives'][0]['id']
    def act(operation, **fields):
        return objectives.mutate(monorepo, 'demo', {'type':operation,'objective_id':oid,**fields})['objectives'][0]
    task = act('task', title='Read the document')['tasks'][0]
    refs = []
    for section in ('Overview', 'Evidence', 'Decisions'):
        resource = act('resource', kind='link', title=section,
                       url='https://docs.google.com/document/d/example/edit#heading='+section.lower())['resources'][-1]
        refs.append(resource['id'])
        act('asset-star', resource_id=resource['id'], starred=True)
        act('task-asset', task_id=task['id'], resource_id=resource['id'])
    fixture = {'folder':str(folder),'oid':oid,'task':task['id'],'a':refs[0],'b':refs[1],'c':refs[2]}
    scripts = ''.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js','js/lib/workspace-objectives.js'])
    css = (STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/workspace-objectives.css').read_text()
    setup = r'''
window.errors=[];window.opened=[];
window.addEventListener('error',e=>errors.push(e.error?.stack||e.message));
window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
window.assert=(ok,msg)=>{if(!ok)throw Error(msg)};
window.until=async fn=>{for(let i=0;i<250;i++){if(await fn())return;await new Promise(r=>setTimeout(r,20))}throw Error('Timeout: '+fn+' '+JSON.stringify(errors))};
window.read=()=>fetch('/api/objectives?workspace_id=demo').then(r=>r.json());
window.act=async fields=>{const d=await read(),r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{objective_id:FIX.oid,...fields}})});assert(r.ok,'fixture mutation');await LabObjectives.load(undefined,true);return r.json()};
window.explorerToast=(message,error)=>{if(error)errors.push(message)};
window.LabExternalLinks={open:(url,options)=>opened.push({url,options})};
LabObjectives.connect({context:()=>({workspace_id:'demo',path:FIX.folder}),scopeRoot:()=>FIX.folder,readyContent:()=>Promise.resolve(),prepareCenter(){},refreshTabs:()=>document.getElementById('tabs').innerHTML=LabObjectives.tabsHtml(FIX.folder)});
(async()=>{await LabObjectives.load();LabObjectives.selectObjective(FIX.oid);window.original=(await read()).objectives[0];window.ready=true})().catch(e=>errors.push(e.stack));
'''
    page = '<!doctype html><meta charset="utf-8"><style>'+css+'''
body{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#e6edf3;--text-secondary:#a6afb9;--text-dim:#8b949e;--accent:#58a6ff;margin:0;background:var(--bg-primary)}
#sidebar{position:static;width:320px;height:calc(100vh - 42px);overflow:auto}#content{min-width:0;height:calc(100vh - 42px);overflow:auto}.test-layout{display:grid;grid-template-columns:320px 1fr}.repo-tabs{position:static;top:auto;height:42px}
</style><div class="repo-tabs" id="tabs"></div><div class="test-layout"><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main></div>'''+scripts+'<script>const FIX='+json.dumps(fixture)+';'+setup+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            response = client.get(self.path) if self.path.startswith('/api/') else None
            body = response.content if response is not None else page.encode()
            self.send_response(response.status_code if response is not None else 200)
            self.send_header('Content-Type','application/json' if response is not None else 'text/html')
            self.end_headers();self.wfile.write(body)
        def do_POST(self):
            response = client.post(self.path,json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
    server = HTTPServer(('127.0.0.1',0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser error');return r.result.value};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const point=selector=>evaluate(`(async()=>{const n=document.querySelector(${JSON.stringify(selector)});assert(n,'target '+${JSON.stringify(selector)});n.scrollIntoView({block:'center'});await new Promise(requestAnimationFrame);const r=n.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
 const move=async selector=>{const p=selector?await point(selector):{x:1300,y:900};await send('Input.dispatchMouseEvent',{type:'mouseMoved',...p});return p};
 const click=async(selector,button='left')=>{const p=await move(selector);await evaluate(`assert(document.elementFromPoint(${p.x},${p.y})?.closest(${JSON.stringify(selector)}),'hittable '+${JSON.stringify(selector)})`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button,clickCount:1})};
 const sidebar='[data-objective-bucket=objective]', group=sidebar+' [data-asset-group]', toggle=group+' [data-asset-group-toggle]', children=group+' > .objective-asset-group-children';
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<250;i++){if(await evaluate('!!window.ready'))break;await sleep(20)}
 await evaluate(`assert(window.ready,'page loaded '+JSON.stringify(window.errors))`);
 await evaluate(`assert(!errors.length&&!document.querySelector('[data-asset-group]'),'no automatic grouping')`);
 const FIX=await evaluate('FIX');
 const menu=resource=>sidebar+' [data-asset-layout-item]:has([data-objective-resource="'+resource+'"]) .objective-asset-menu';
 await click(menu(FIX.a));await click('[data-group-asset]');
 await evaluate(`document.querySelector('.objective-dialog [name=title]').value='Google Doc sections'`);await click('.objective-dialog [type=submit]');
 await evaluate(`until(()=>document.querySelector('[data-asset-group]')&&!document.querySelector('.objective-dialog[open]'))`);
 const gid=await evaluate(`document.querySelector('[data-asset-group]').dataset.assetGroup`);
 await click(menu(FIX.b));await click('[data-group-asset]');
 await evaluate(`const n=document.querySelector('.objective-dialog [name=group]');n.value=${JSON.stringify(gid)};n.dispatchEvent(new Event('change'));assert(!document.querySelector('[name=title]').required,'existing group needs no new name')`);
 await click('.objective-dialog [type=submit]');await evaluate(`until(async()=>(await read()).objectives[0].asset_groups[0].assets.length===2&&!document.querySelector('.objective-dialog[open]'))`);
 await move();await evaluate(`document.activeElement.blur()`);await move(toggle);await sleep(250);
 await evaluate(`assert(document.querySelector(${JSON.stringify(children)}).hidden,'hold before opening')`);
 await move();await sleep(850);await evaluate(`assert(document.querySelector(${JSON.stringify(children)}).hidden,'leave cancels opening')`);
 await move(toggle);await sleep(550);
 await evaluate(`act({type:'asset-group-rename',group_id:${JSON.stringify(gid)},title:'Document sections'})`);
 await sleep(120);await evaluate(`assert(document.querySelector(${JSON.stringify(children)}).hidden,'repaint cannot open early')`);
 await sleep(450);await evaluate(`assert(!document.querySelector(${JSON.stringify(children)}).hidden,'one second hover survives repaint');assert(!document.querySelector(${JSON.stringify(children)}+' [data-asset-group]'),'one flat level')`);
 await evaluate(`act({type:'asset-group-rename',group_id:${JSON.stringify(gid)},title:'Google Doc sections'})`);
 await evaluate(`assert(!document.querySelector(${JSON.stringify(children)}).hidden,'open hover survives repaint')`);
 const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(process.argv[1]+'/asset-groups.png',Buffer.from(shot.data,'base64'));
 await click(children+' [data-objective-resource="'+FIX.b+'"]','right');
 await click('[data-asset-order]:not(:disabled)');await evaluate(`until(async()=>(await read()).objectives[0].asset_groups[0].assets[0].resource_id===FIX.b)`);
 await click(toggle);await click(children+' [data-objective-resource="'+FIX.b+'"]');
 await evaluate(`assert(opened.at(-1).url==='https://docs.google.com/document/d/example/edit#heading=evidence'&&opened.at(-1).options.popup,'exact Google Doc section opens in popup')`);
 await click(group+' [data-asset-group-menu]');await click('[data-asset-order]:not(:disabled)');
 await evaluate(`until(async()=>(await read()).objectives[0].asset_order[0].resource_id===FIX.c)`);
 await move();await evaluate(`document.activeElement.blur();LabObjectives.load(undefined,true)`);
 await evaluate(`assert(document.querySelector(${JSON.stringify(sidebar)}+' [data-asset-layout-item]').dataset.assetLayoutItem.includes(FIX.c),'root order persists');assert(document.querySelector(${JSON.stringify(children)}).hidden,'fresh hover stays collapsed')`);
 await click(toggle);
 await click(children+' [data-objective-resource="'+FIX.b+'"]','right');await click('[data-group-asset]');await click('.objective-dialog [type=submit]');
 await evaluate(`until(()=>!document.querySelector('.objective-dialog[open]'));assert(document.querySelector(${JSON.stringify(children)}+' [data-objective-resource]').dataset.objectiveResource===FIX.b,'same group save keeps child order')`);
 await evaluate(`(()=>{const header=document.querySelector(${JSON.stringify(group)}+' [data-asset-group-header]'),dt=new DataTransfer();dt.setData('application/x-lab-objective-resource',JSON.stringify({scope:'::demo',objective_id:FIX.oid,resource_id:FIX.c}));header.dispatchEvent(new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer:dt}));assert(header.classList.contains('objective-drop-target'),'group is a highlighted drop target');header.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}))})()`);
 await evaluate(`until(async()=>(await read()).objectives[0].asset_groups[0].assets.length===3)`);
 await click(toggle);await click(children+' [data-objective-resource="'+FIX.b+'"]','right');await click('[data-remove-asset-group]');
 await evaluate(`until(async()=>(await read()).objectives[0].asset_groups[0].assets.length===2)`);
 await click(group+' [data-asset-group-menu]');await click('[data-rename-asset-group]');
 await evaluate(`document.querySelector('.objective-dialog [name=title]').value='Grouped sections'`);await click('.objective-dialog [type=submit]');
 await evaluate(`until(()=>document.querySelector(${JSON.stringify(toggle)})?.textContent.includes('Grouped sections')&&!document.querySelector('.objective-dialog[open]'))`);
 await click(group+' [data-asset-group-menu]');await click('[data-ungroup-assets]');
 await evaluate(`(async()=>{await until(()=>!document.querySelector('[data-asset-group]'));const o=(await read()).objectives[0];for(const key of ['resources','tasks','shared_assets'])assert(JSON.stringify(o[key])===JSON.stringify(original[key]),'grouping preserves '+key);assert(!errors.length,'no errors '+JSON.stringify(errors))})()`);
 ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        for _ in range(150):
            if (profile/'DevToolsActivePort').exists():
                break
            if process.poll() is not None:
                pytest.fail('Chrome exited before startup')
            time.sleep(.05)
        result = subprocess.run(['node','-e',driver,str(profile),f'http://127.0.0.1:{server.server_port}'],capture_output=True,text=True,timeout=60)
        assert result.returncode == 0, result.stdout+result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
