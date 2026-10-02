"""The real Objective API and native editor preserve drafts across tab saves."""
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

STATIC = Path(__file__).resolve().parents[2] / 'core/src/core/static'


def test_objective_inline_editor_serializes_sibling_saves_and_retains_conflicts(client, monorepo, seed_workspace, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    folder = seed_workspace()
    data = objectives.mutate(monorepo, 'demo', {'type':'create','name':'Editor project'})
    oid = data['objectives'][0]['id']
    data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':'document','title':'Editor','body':'# Document\n\n**Bold** text.\n'})
    rid = data['objectives'][0]['resources'][0]['id']
    for name in ['Child','Sibling']:
        data = objectives.mutate(monorepo, 'demo', {'type':'subtab','objective_id':oid,'resource_id':rid,'title':name,'body':name+' source'})
    resource = data['objectives'][0]['resources'][0]
    fixture = {'folder':str(folder),'oid':oid,'rid':rid,'child':resource['content']['tabs'][0]['id']}
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','vendor/lab-markdown-editor/markdown-editor.min.js','js/lib/workspace-objectives.js'])
    setup = r'''
window.assert=(ok,message)=>{if(!ok)throw Error(message)};
window.until=async fn=>{for(let i=0;i<800;i++){if(await fn())return;await new Promise(r=>setTimeout(r,25))}throw Error('Timed out: '+fn)};
const makeEditor=LabMarkdownEditor.create;window.editors=[];
LabMarkdownEditor.create=(parent,options)=>{const input=makeEditor(parent,options);editors.push(input);return input};
window.editor=()=>editors.find(input=>input.view.dom.isConnected);
const realFetch=window.fetch.bind(window);
window.fetch=async(url,options={})=>{
 const response=await realFetch(url,options);
 if(window.hold&&options.method==='POST'&&JSON.parse(options.body).action.type==='document'){
   window.hold=false;await new Promise(resolve=>window.release=resolve);
 }
 return response;
};
window.read=()=>realFetch('/api/objectives?workspace_id=demo').then(r=>r.json());
window.resource=data=>data.objectives[0].resources[0];
LabObjectives.connect({context:()=>({workspace_id:'demo',path:FIX.folder}),readyContent:()=>Promise.resolve(),prepareCenter:()=>{},selectWorktree:()=>{}});
(async()=>{await LabObjectives.load();LabObjectives.selectObjective(FIX.oid);document.getElementById('result').textContent='READY'})().catch(e=>document.getElementById('result').textContent=e.stack);
'''
    page = '<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/workspace-objectives.css').read_text()+'</style><div id="sidebar"><section data-objectives-sidebar></section></div><main id="content"></main><pre id="result">PENDING</pre>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+setup+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.startswith('/api/'):
                response=client.get(self.path); data,code,kind=response.content,response.status_code,'application/json'
            else:
                data,code,kind=page.encode(),200,'text/html'
            self.send_response(code);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(data)
        def do_POST(self):
            response=client.post(self.path,json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
    server=HTTPServer(('127.0.0.1',0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    profile=tmp_path/'profile'
    process=subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0;
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 async function click(selector){const p=await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});assert(n,'click target');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 async function type(text){await evaluate('editor().view.dispatch({selection:{anchor:editor().value.length},scrollIntoView:true});editor().focus()');await send('Input.insertText',{text});}
 await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<200;i++){if(await evaluate('!!window.until'))break;await new Promise(r=>setTimeout(r,20));}
 await evaluate(`until(()=>document.getElementById('result').textContent==='READY')`);
 await click('[data-objective-resource]');
 await evaluate(`assert(editor()&&document.querySelector('.cm-content strong')?.textContent==='Bold','live editor on open');assert(getComputedStyle(editor().view.dom).fontSize==='13px','native text size');assert(document.querySelector('.objective-selectors').nextElementSibling.hasAttribute('data-open-objective-tasks'),'Tasks below projects');assert(document.querySelectorAll('[data-objective-root]').length===2,'two fixed roots');assert(document.querySelectorAll('.objective-document [role=tablist]').length===0,'tabs outside content')`);
 await type('\nFirst submitted edit.');
 await evaluate('window.hold=true');await click('[data-save-objective-document]');
 await evaluate('until(()=>window.release)');
 await type('\nNewer edit during save.');
 await click('[data-objective-tab]');await type('\nChild edit during parent save.');
 await evaluate('release()');await click('[data-save-objective-document]');
 await evaluate(`(async()=>{await until(async()=>{const r=resource(await read());return r.content.body.includes('Newer edit during save.')&&r.content.tabs[0].body.includes('Child edit during parent save.')});assert(resource(await read()).content.tabs[1].body==='Sibling source','sibling stays intact');assert(editor().value.includes('Child edit'),'late save keeps selected editor')})()`);
 await type('\nIdle autosave edit.');
 await evaluate(`until(async()=>resource(await read()).content.tabs[0].body.includes('Idle autosave edit.'))`);
 await type('\nRetained conflicting draft.');
 await evaluate(`(async()=>{const d=await read(),r=resource(d);const response=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'document',objective_id:FIX.oid,resource_id:FIX.rid,tab_id:FIX.child,document_revision:r.content.revision,body:r.content.tabs[0].body+'\\nConcurrent edit.'}})});assert(response.ok,'external write')})()`);
 await click('[data-save-objective-document]');
 await evaluate(`(async()=>{await until(()=>document.querySelector('.objective-document-status').classList.contains('error'));assert(editor().value.includes('Retained conflicting draft.'),'conflict retains draft');assert(!resource(await read()).content.tabs[0].body.includes('Retained conflicting draft.'),'conflict never overwrites')})()`);
 await click('[data-revert-objective-document]');
 await evaluate(`(async()=>{await until(()=>editor().value.includes('Concurrent edit.')&&!document.querySelector('.objective-document-status').classList.contains('error'));assert(resource(await read()).content.tabs[1].body==='Sibling source','recovery keeps sibling')})()`);
 ws.close();console.log('PASS');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    try:
        for _ in range(150):
            if (profile/'DevToolsActivePort').exists(): break
            if process.poll() is not None: pytest.fail('Chrome exited before startup')
            time.sleep(.05)
        result=subprocess.run(['node','-e',driver,str(profile),f'http://127.0.0.1:{server.server_port}'],capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
