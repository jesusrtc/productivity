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
    checkout = tmp_path/'other checkout';checkout.mkdir()
    data = objectives.mutate(monorepo, 'demo', {'type':'worktree','objective_id':oid,'path':str(checkout),'kind':'folder'})
    for filename, body in [('copied.ipynb', '{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}'), ('query.sql', 'SELECT 1;')]:
        (folder/filename).write_text(body)
        data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':'file','title':filename,'path':filename})
    for kind, title, extra in [('notebook','Analysis',{}),('link','External',{'url':'https://example.com/a?one=1&two=2#section'})]:
        data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':kind,'title':title,**extra})
    file = folder/'existing file.py';file.write_text('print(1)\n')
    data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':'file','title':'Existing file','path':file.name})
    from core.routes import term
    term._upsert_workspace_session(monorepo,'demo',{'name':'native-drag-shell','kind':'terminal','cwd':str(folder),'agent_session_id':'preserved'})
    saved_session=term._get_workspace_sessions(monorepo,'demo')[0]
    fixture = {'folder':str(folder),'oid':oid,'rid':rid,'child':resource['content']['tabs'][0]['id'],'checkout':str(checkout),'session':saved_session,'editorPath':resource['path']}
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
const pasted=[],termXterm={paste:text=>pasted.push(text),focus(){}},termWS={readyState:1};
const _termDragState=null,workspaceTabsDragId=null;
const notices=[],opened=[];let scopeRoot=FIX.folder;
window.explorerToast=(message,error)=>{if(error)throw Error(message);notices.push(message)};
document.getElementById('termBody').addEventListener('drop',_termHandleDrop);
document.addEventListener('dragstart',event=>{if(event.isTrusted&&!event.target.closest('[data-drag-objective]')){window.nativeDrag={effect:event.dataTransfer.effectAllowed,reference:event.dataTransfer.getData('application/x-lab-reference')};event.preventDefault()}});
window.checkDrag=(selector,expected)=>{
 const node=document.querySelector(selector),transfer=new DataTransfer();assert(node?.draggable,'draggable '+selector);
 node.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 assert(JSON.parse(transfer.getData('application/x-lab-reference'))[0]===expected,'captured reference '+selector);
 const count=pasted.length;
 document.getElementById('termBody').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 assert(pasted.length===count+1&&pasted.at(-1)===_termQuoteDropPath(expected),'unsent console paste '+selector);
};
window.checkLink=async(selector,expected)=>{
 const node=document.querySelector(selector),transfer=new DataTransfer();
 node.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 const count=pasted.length;
 document.querySelector('#termSessionList .sess').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 await until(async()=>{const link=(await read()).terminal_links[FIX.session.session_id];return link&&Object.entries(expected).every(([key,value])=>JSON.stringify(link[key])===JSON.stringify(value))});
 assert(pasted.length===count,'association never writes terminal input');
 await LabObjectives.load(undefined,true);assert(LabObjectives.openForTerminal(FIX.session),'linked terminal opens target');
};
LabObjectives.connect({fileIcon:fileIconHtml,context:()=>({workspace_id:'demo',path:FIX.folder}),refreshTabs:()=>document.getElementById('tabs').innerHTML=LabObjectives.tabsHtml(FIX.folder),readyContent:()=>Promise.resolve(),prepareCenter:()=>{},scopeRoot:()=>scopeRoot,selectWorktree:row=>{scopeRoot=row.path},session:name=>name===FIX.session.name?FIX.session:null,openLink:link=>opened.push({url:link.url}),openFile:file=>opened.push({file}),openNotebook:r=>opened.push({notebook:r.path}),openFolder:folder=>opened.push({folder})});
(async()=>{await LabObjectives.load();LabObjectives.selectObjective(FIX.oid);document.getElementById('result').textContent='READY'})().catch(e=>document.getElementById('result').textContent=e.stack);
'''
    app = (STATIC/'js/lab-app.js').read_text()
    setup = app[app.index('  function fileIconHtml('):app.index('  function buildSidebarTree(')] + app[app.index('  function _termDropPaths('):app.index('  function _termReflowSelection(')] + setup
    page = '<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/workspace-objectives.css').read_text()+'body{padding-top:90px}</style><div class="repo-tabs" id="tabs"></div><div id="sidebar"><section data-objectives-sidebar></section></div><main id="content"></main><div id="termSessionList"><button class="sess" data-name="'+saved_session['name']+'">Shell</button></div><div id="termBody"></div><pre id="result">PENDING</pre>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+setup+'</script>'
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
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let sequence=0,dragData=null;
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 async function click(selector){const p=await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});assert(n,'click target');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});}
 async function type(text){await evaluate('editor().view.dispatch({selection:{anchor:editor().value.length},scrollIntoView:true});editor().focus()');await send('Input.insertText',{text});}
 await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<200;i++){if(await evaluate('!!window.until'))break;await new Promise(r=>setTimeout(r,20));}
 await evaluate(`until(()=>document.getElementById('result').textContent==='READY')`);
 await evaluate(`(async()=>{const d=await read(),o=d.objectives[0];for(const r of o.resources)checkDrag('[data-objective-resource="'+r.id+'"]',r.kind==='link'?r.url:(r.file_root||FIX.folder)+'/'+r.path);checkDrag('[data-open-objective-tasks]',FIX.folder+'/.lab/objectives.json#objective='+FIX.oid+'&view=tasks');checkDrag('[data-select-worktree="workspace-root"]',FIX.folder);checkDrag('[data-select-worktree="objective-root"]',o.path);checkDrag('[data-objective-worktree] [data-select-worktree]',FIX.checkout);const result=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'task',objective_id:FIX.oid,title:'Task with details'}})});assert(result.ok,'task creation');await LabObjectives.load(undefined,true);const updated=await read(),task=updated.objectives[0].tasks[0],resource=updated.objectives[0].resources.find(r=>r.id===task.document_id);checkDrag('[data-open-objective-tasks]',FIX.folder+'/'+resource.path)})()`);
 const dragPoint=await evaluate(`(()=>{const n=document.querySelector('[data-objective-resource]');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+Math.min(40,r.width/2),y:r.y+r.height/2}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...dragPoint});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...dragPoint,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:dragPoint.x+20,y:dragPoint.y+4,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:dragPoint.x+40,y:dragPoint.y+8,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:dragPoint.x+40,y:dragPoint.y+8,button:'left',clickCount:1});
 await evaluate(`assert(nativeDrag.effect==='copyLink'&&JSON.parse(nativeDrag.reference)[0]===FIX.folder+'/'+FIX.editorPath,'trusted native drag carries source and supports copy or association')`);
 await evaluate(`(async()=>{for(const r of (await read()).objectives[0].resources)await checkLink('[data-objective-resource="'+r.id+'"]',{resource_id:r.id});assert(opened.some(o=>o.url==='https://example.com/a?one=1&two=2#section')&&opened.some(o=>o.notebook)&&opened.some(o=>o.file),'links, notebooks and files reopen');await checkLink('[data-open-objective-tasks]',{view:'tasks'});assert(document.querySelector('.objective-working h2').textContent==='Tasks','Tasks association opens task list');for(const [id,root] of [['workspace-root',FIX.folder],['objective-root',(await read()).objectives[0].path]]){await checkLink('[data-select-worktree="'+id+'"]',{folder:{root,path:'.'}});await until(()=>opened.some(o=>o.folder?.root===root));assert(scopeRoot===root,'folder association selects sidebar scope')}await checkLink('[data-objective-worktree] [data-select-worktree]',{folder:{root:FIX.checkout,path:'.'}});await until(()=>opened.some(o=>o.folder?.root===FIX.checkout));assert(scopeRoot===FIX.checkout,'worktree association selects captured checkout');const transfer=new DataTransfer();transfer.setData('application/x-lab-file-path',JSON.stringify([FIX.folder+'/existing file.py']));transfer.setData('application/x-lab-file-context',JSON.stringify({kind:'file',root:FIX.folder,path:'existing file.py'}));document.querySelector('#termSessionList .sess').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await until(async()=>{const link=(await read()).terminal_links[FIX.session.session_id];return link.file?.root===FIX.folder&&link.file.path==='existing file.py'});assert(pasted.every(p=>!p.includes('\\n')),'no submitted drops')})()`);
 await click('[data-objective-resource]');
 await evaluate(`checkDrag('[data-objective-tab="'+FIX.child+'"]',FIX.folder+'/'+FIX.editorPath+'#tab='+FIX.child)`);
 await evaluate(`checkLink('[data-objective-tab="'+FIX.child+'"]',{resource_id:FIX.rid,tab_id:FIX.child})`);
 await click('[data-objective-resource]');
 await evaluate(`assert(document.querySelectorAll('.objective-resource .ft-nb').length===2&&document.querySelector('.objective-resource .ft-sql'),'owned and generic notebook / SQL icons follow paths');assert(editor()&&document.querySelector('.cm-content strong')?.textContent==='Bold','live editor on open');assert(getComputedStyle(editor().view.dom).fontSize==='13px','native text size');assert(document.querySelector('[data-objectives-sidebar]').firstElementChild.hasAttribute('data-open-objective-tasks'),'Tasks at sidebar top');assert(document.querySelectorAll('[data-objective-root]').length===2,'two fixed roots');assert(document.querySelectorAll('.repo-tabs .objective-tab').length===2&&document.querySelector('[data-all-objectives]').textContent==='Objectives','Objectives and one current tab');assert(!document.querySelector('.objective-selectors'),'no duplicate sidebar selectors');assert(document.querySelectorAll('.objective-document [role=tablist]').length===0,'tabs outside content')`);
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
 await click('[data-all-objectives]');
 await evaluate(`assert(document.querySelectorAll('.objective-focus-slots [data-objective-slot]').length===5,'five slots in library');document.querySelector('[data-current-objective]').focus()`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
 await evaluate(`assert(document.querySelectorAll('.objective-switch-menu button').length===5,'five dropdown choices');assert(document.activeElement.closest('.objective-switch-menu'),'keyboard enters dropdown');assert(document.querySelector('.objective-switch-menu').getBoundingClientRect().top>=document.querySelector('.repo-tabs').getBoundingClientRect().bottom-4,'menu escapes scrolling tab strip')`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await evaluate(`assert(!document.querySelector('.objective-switch-menu')&&document.activeElement.hasAttribute('data-current-objective'),'Escape closes and restores focus')`);
 await click('[data-objective-search]');
 await send('Input.insertText',{text:'does-not-exist'});
 await evaluate(`assert(!document.querySelector('.objective-library-row')&&document.querySelector('.objective-library-list').textContent.includes('No objectives match'),'native search filters rows');document.querySelector('[data-objective-search]').select()`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
 await evaluate(`assert(document.querySelectorAll('.objective-library-row').length===1,'clearing search restores rows')`);
 await click('[data-objective-slot="4"]');await click('.objective-dialog [type=submit]');
 await evaluate(`(async()=>{await until(async()=>{const d=await read();return d.focused[4]===FIX.oid&&!d.focused[0]});const d=await read();assert(document.querySelector('[data-objective-slot="4"]').dataset.selectObjective===FIX.oid,'empty slot assigns exact position');assert(document.querySelector('.objective-working h2').textContent==='All objectives','slot placement keeps library open');assert(document.querySelector('[data-current-objective]').style.getPropertyValue('--vault-color')===d.slot_palettes[4][0],'current tab follows slot color');assert(resource(await read()).content.tabs[1].body==='Sibling source','slot changes keep document')})()`);
 await evaluate(`(async()=>{for(const name of ['Second','Third','Fourth','Fifth','Sixth']){const d=await read(),r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'create',name,slot:0}})});assert(r.ok,'fixture objective');}const d=await read();window.beforeInsertion=d.focused.slice();await LabObjectives.load(undefined,true);assert(!d.focused.includes(FIX.oid),'fixture parked');document.getElementById('sidebar').style.display='none';window.scrollTo(0,0)})()`);
 const points=await evaluate(`(()=>{const source=document.querySelector('[data-drag-objective="'+FIX.oid+'"]'),target=document.querySelector('[data-objective-slot="0"]');const a=source.getBoundingClientRect(),b=target.getBoundingClientRect();assert(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)?.closest('[data-objective-slot]')===target,'visible native drop target '+JSON.stringify({a,b}));return{source:{x:a.x+20,y:a.y+a.height/2},target:{x:b.x+b.width/2,y:b.y+b.height/2}}})()`);
 await send('Input.setInterceptDrags',{enabled:true});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...points.source});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...points.source,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:points.source.x+25,y:points.source.y,button:'left',buttons:1});
 for(let i=0;i<100&&!dragData;i++)await new Promise(r=>setTimeout(r,20));
 if(!dragData?.items.some(item=>item.mimeType==='application/x-lab-workspace-objective'))throw Error('Native objective drag payload');
 for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...points.target,data:dragData});
 await send('Input.setInterceptDrags',{enabled:false});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',...points.target,button:'left',clickCount:1});
 await evaluate(`(async()=>{await until(async()=>{const d=await read();return d.focused[0]===FIX.oid});const d=await read();assert(JSON.stringify(d.focused)===JSON.stringify([FIX.oid,...beforeInsertion.slice(0,4)]),'trusted drag inserts and pushes fifth out');assert(document.querySelector('.objective-library'),'native drop keeps library');assert(resource(d).content.tabs[1].body==='Sibling source','parking and refocus keep sibling document');assert(d.objectives[0].worktrees[0].color===d.slot_palettes[0][0],'refocused worktree inherits slot palette')})()`);
 const hover=await evaluate(`(()=>{const r=document.querySelector('[data-current-objective]').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...hover});
 await evaluate(`until(()=>document.querySelectorAll('.objective-switch-menu [data-select-objective]').length===5)`);
 await click('.objective-switch-menu button:nth-child(2)');
 await evaluate(`assert(document.querySelector('.objective-working h2').textContent==='Tasks'&&!document.querySelector('.objective-switch-menu'),'hover choice switches objective and closes menu');assert(document.querySelector('[data-current-objective]').style.getPropertyValue('--vault-color')==='#bc8cff','selected second slot color')`);
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
        assert term._get_workspace_sessions(monorepo,'demo') == [saved_session]
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
