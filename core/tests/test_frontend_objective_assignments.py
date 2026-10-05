"""Native browser review, search, classification and sidebar visibility."""
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


def test_objective_asset_review_and_context_menu(client, monorepo, seed_workspace, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    folder = seed_workspace()
    oid = objectives.mutate(monorepo, 'demo', {'type':'create', 'name':'Review project'})['objectives'][0]['id']
    def act(operation, **fields):
        return objectives.mutate(monorepo, 'demo', {'type':operation, 'objective_id':oid, **fields})
    alpha = act('task', title='Alpha analysis')['objectives'][0]['tasks'][0]
    empty = act('task', title='Empty task')['objectives'][0]['tasks'][1]
    loose = act('resource', kind='link', title='Loose reference', url='https://example.com/loose')['objectives'][0]['resources'][-1]
    pinned = act('resource', kind='link', title='Pinned handbook', url='https://example.com/pinned')['objectives'][0]['resources'][-1]
    act('asset-star', resource_id=pinned['id'], starred=True)
    (folder/'query.sql').write_text('SELECT 1;')
    sql = act('resource', kind='file', title='query.sql', path='query.sql')['objectives'][0]['resources'][-1]
    companion = act('resource', kind='link', title='Companion evidence', url='https://example.com/companion')['objectives'][0]['resources'][-1]
    for resource in (sql, companion):
        act('task-asset', resource_id=resource['id'], task_id=alpha['id'])
    data = act('suggest-assignment', resource_id=loose['id'], destination={'bucket':'task', 'task_id':alpha['id']}, reason='Evidence needed for Alpha')
    sid = data['objectives'][0]['assignment_suggestions'][0]['id']
    fixture = {'folder':str(folder), 'oid':oid, 'alpha':alpha['id'], 'empty':empty['id'],
               'loose':loose['id'], 'pinned':pinned['id'], 'sql':sql['id'], 'companion':companion['id'], 'sid':sid}
    scripts = ''.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'vendor/lab-markdown-editor/markdown-editor.min.js', 'js/lib/workspace-objectives.js'])
    setup = r'''
window.errors=[];
window.addEventListener('error',e=>errors.push(e.error?.stack||e.message));
window.addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
window.assert=(ok,msg)=>{if(!ok)throw Error(msg)};
window.until=async fn=>{for(let i=0;i<300;i++){if(await fn())return;await new Promise(r=>setTimeout(r,20))}throw Error('Timeout: '+fn)};
window.read=()=>fetch('/api/objectives?workspace_id=demo').then(r=>r.json());
window.act=async fields=>{const d=await read(),r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{objective_id:FIX.oid,...fields}})});assert(r.ok,'fixture mutation');await LabObjectives.load(undefined,true);return r.json()};
window.explorerToast=(msg,error)=>{if(error)errors.push(msg)};
LabObjectives.connect({context:()=>({workspace_id:'demo',path:FIX.folder}),scopeRoot:()=>FIX.folder,
 readyContent:()=>Promise.resolve(),prepareCenter(){},refreshTabs:()=>document.getElementById('tabs').innerHTML=LabObjectives.tabsHtml(FIX.folder)});
(async()=>{await LabObjectives.load();LabObjectives.selectObjective(FIX.oid);window.ready=true})().catch(e=>errors.push(e.stack));
'''
    css = (STATIC/'css/lab-shell.css').read_text() + (STATIC/'css/workspace-objectives.css').read_text()
    page = '<!doctype html><meta charset="utf-8"><style>'+css+'''
body{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--border:#30363d;--text-primary:#e6edf3;--text-secondary:#a6afb9;--text-dim:#8b949e;--accent:#58a6ff;margin:0;background:var(--bg-primary)}
#sidebar{position:static;width:300px;height:calc(100vh - 42px);overflow:auto}#content{min-width:0;height:calc(100vh - 42px);overflow:auto}.test-layout{display:grid;grid-template-columns:300px 1fr}.repo-tabs{position:static;top:auto;height:42px}
</style><div class="repo-tabs" id="tabs"></div><div class="test-layout"><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main></div>''' + scripts + '<script>const FIX='+json.dumps(fixture)+';</script><script>'+setup+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            response = client.get(self.path) if self.path.startswith('/api/') else None
            body = response.content if response else page.encode()
            self.send_response(response.status_code if response else 200)
            self.send_header('Content-Type', 'application/json' if response else 'text/html')
            self.end_headers();self.wfile.write(body)
        def do_POST(self):
            response = client.post(self.path, json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
    server = HTTPServer(('127.0.0.1',0), Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome, '--headless=new', '--no-first-run', '--remote-debugging-port=0',
                                '--user-data-dir='+str(profile), 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
 const click=async(selector,button='left')=>{const p=await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});assert(n,'click target '+${JSON.stringify(selector)});n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button,clickCount:1})};
 const search=async text=>{await evaluate(`(()=>{const n=document.querySelector('[data-objective-overview-search]');n.focus();n.select()})()`);await send('Input.insertText',{text});};
 const mode=async value=>evaluate(`(()=>{const n=document.querySelector('[data-objective-overview-mode]');n.value=${JSON.stringify(value)};n.dispatchEvent(new Event('change',{bubbles:true}))})()`);
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<200;i++){if(await evaluate('!!window.ready'))break;await new Promise(r=>setTimeout(r,20))}
 await evaluate(`assert(ready&&!errors.length,'ready without errors');assert(document.querySelector('[data-objective-overview-results]').firstElementChild.getAttribute('aria-label')==='Unassigned assets','unassigned first');assert(document.querySelector('[data-accept-assignment]')&&document.querySelector('[data-reject-assignment]'),'review controls');const buckets=[...document.querySelectorAll('[data-objectives-sidebar]>[data-objective-bucket]')].map(n=>n.dataset.objectiveBucket);assert(buckets[0]==='objective'&&buckets[1]==='tasks','pinned above tasks');assert([...document.querySelectorAll('[data-overview-task]')][0].dataset.overviewTask===FIX.empty,'tasks without attachments first')`);
 await search('Alpha');
 await evaluate(`assert(document.activeElement.hasAttribute('data-objective-overview-search'),'typing preserves focus');assert(document.querySelectorAll('[data-overview-task]').length===1,'task search filters tasks');assert(document.querySelector('[data-overview-task="'+FIX.alpha+'"] [data-objective-resource="'+FIX.sql+'"]')&&document.querySelector('[data-overview-task="'+FIX.alpha+'"] [data-objective-resource="'+FIX.companion+'"]'),'matching task shows all its assets')`);
 await search('query.sql');
 await evaluate(`assert(document.querySelector('[data-overview-task="'+FIX.alpha+'"]'),'asset match shows owner task');assert(document.querySelectorAll('[data-overview-task]').length===1,'unrelated tasks filtered')`);
 await mode('tasks');await evaluate(`assert(document.querySelector('[data-overview-task="'+FIX.alpha+'"]')&&!document.querySelector('.objective-review-asset'),'tasks-only view')`);
 await mode('assets');await search('');
 const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(process.argv[1]+'/objective-review.png',Buffer.from(shot.data,'base64'));
 await click('[data-reject-assignment]');
 await evaluate(`until(()=>document.querySelector('.objective-review-asset')?.textContent.includes('Suggestion rejected'))`);
 await evaluate(`(async()=>{const o=(await read()).objectives[0];assert(!o.tasks[0].assets.some(a=>a.resource_id===FIX.loose),'reject never assigns');await act({type:'suggest-assignment',resource_id:FIX.loose,destination:{bucket:'task',task_id:FIX.empty},reason:'Useful for the empty task'})})()`);
 await click('[data-accept-assignment]');
 await evaluate(`until(async()=>(await read()).objectives[0].tasks[1].assets?.some(a=>a.resource_id===FIX.loose))`);
 await evaluate(`until(()=>!document.querySelector('[data-accept-assignment]'))`);
 const source=await evaluate(`'[data-overview-task="'+FIX.empty+'"] [data-objective-resource="'+FIX.loose+'"]'`);
 await click(source,'right');await evaluate(`assert(document.querySelector('.objective-asset-context-menu [data-menu-assignment="task"]')&&document.querySelector('[data-menu-assignment="objective"]')&&document.querySelector('[data-menu-bucket="archive"]')&&document.querySelector('.objective-asset-context-menu [data-trash-objective-asset]'),'right-click actions')`);
 await click('[data-menu-assignment="task"]');
 await evaluate(`const n=document.querySelector('.objective-dialog [name=task]');n.value=FIX.alpha;assert(document.querySelector('[name=bucket]').value==='task','task menu preselects task')`);
 await click('.objective-dialog [type=submit]');
 await evaluate(`until(async()=>{const o=(await read()).objectives[0];return o.tasks[0].assets.some(a=>a.resource_id===FIX.loose)&&!o.tasks[1].assets.some(a=>a.resource_id===FIX.loose)})`);
 await evaluate(`until(()=>!document.querySelector('.objective-dialog[open]'))`);
 const alphaSource=await evaluate(`'[data-overview-task="'+FIX.alpha+'"] [data-objective-resource="'+FIX.loose+'"]'`);
 await click(alphaSource,'right');await click('[data-menu-bucket="archive"]');
 await evaluate(`until(()=>!document.querySelector('[data-objective-overview-results] [data-objective-resource="'+FIX.loose+'"]'))`);
 await mode('archive');await evaluate(`assert(document.querySelector('[data-restore-objective-asset]')&&document.querySelector('[data-objective-overview-results]').textContent.includes('Loose reference'),'archive view')`);
 await click('[data-restore-objective-asset]');await evaluate(`until(()=>!document.querySelector('[data-restore-objective-asset]'))`);
 await mode('unassigned');await click('[data-trash-objective-asset]');
 await evaluate(`assert(document.querySelector('.objective-dialog[open]'),'trash asks for confirmation')`);
 await click('.objective-dialog [data-cancel]');await evaluate(`assert(document.querySelector('[data-objective-overview-results] [data-objective-resource="'+FIX.loose+'"]'),'cancel keeps asset')`);
 await click('[data-trash-objective-asset]');await click('.objective-dialog [type=submit]');
 await evaluate(`until(async()=>!(await read()).objectives[0].resources.some(r=>r.id===FIX.loose))`);
 await mode('assets');
 const taskLink=await evaluate(`'.objective-sidebar-task [data-open-task="'+FIX.alpha+'"]'`);await click(taskLink);
 await evaluate(`assert(!document.querySelector('[data-objectives-sidebar] [data-objective-bucket=unassigned]')&&!document.querySelector('[data-objectives-sidebar] .objective-archive'),'task focus hides unassigned and archive');assert(document.querySelector('[data-objective-bucket=objective] [data-objective-resource="'+FIX.pinned+'"]'),'pinned remains visible');assert(document.querySelector('[data-objective-bucket=task] [data-objective-resource="'+FIX.sql+'"]'),'task assets remain visible')`);
 await click('.objective-sidebar-heading [data-select-objective]');
 await evaluate(`assert(document.querySelector('[data-objectives-sidebar] [data-objective-bucket=unassigned]'),'Objective reveals unassigned');assert(!errors.length,'no browser errors: '+JSON.stringify(errors))`);
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
