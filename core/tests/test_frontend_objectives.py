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
    # A document's sidebar tree stays available outside the overview when pinned.
    objectives.mutate(monorepo, 'demo', {'type':'asset-star','objective_id':oid,'resource_id':rid,'starred':True})
    for name in ['Child','Sibling']:
        data = objectives.mutate(monorepo, 'demo', {'type':'subtab','objective_id':oid,'resource_id':rid,'title':name,'body':name+' source'})
    resource = data['objectives'][0]['resources'][0]
    checkout = tmp_path/'other checkout';checkout.mkdir()
    data = objectives.mutate(monorepo, 'demo', {'type':'worktree','objective_id':oid,'path':str(checkout),'kind':'folder'})
    for filename, body in [('copied.ipynb', '{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}'), ('query.sql', 'SELECT 1;')]:
        (folder/filename).write_text(body)
        data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':'file','title':filename,'path':filename})
    for kind, title, extra in [('notebook','Analysis',{}),('link','External',{'url':'https://example.com/a?one=1&two=2#section','metadata':{'Owner':'Team','Count':3,'Tags':['a','b']}})]:
        data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':kind,'title':title,**extra})
    file = folder/'existing file.py';file.write_text('print(1)\n')
    data = objectives.mutate(monorepo, 'demo', {'type':'resource','objective_id':oid,'kind':'file','title':'Existing file','path':file.name})
    from core.routes import term
    term._upsert_workspace_session(monorepo,'demo',{'name':'native-drag-shell','kind':'terminal','cwd':str(folder),'agent_session_id':'preserved'})
    saved_session=term._get_workspace_sessions(monorepo,'demo')[0]
    fixture = {'folder':str(folder),'oid':oid,'rid':rid,'child':resource['content']['tabs'][0]['id'],'checkout':str(checkout),'session':saved_session,'editorPath':resource['path']}
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','vendor/lab-markdown-editor/markdown-editor.min.js','js/lib/task-context.js','js/lib/workspace-objectives.js'])
    setup = r'''
window.assert=(ok,message)=>{if(!ok)throw Error(message)};
window.contentErrors=[];
window.addEventListener('error',event=>contentErrors.push(event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>contentErrors.push(String(event.reason)));
window.until=async fn=>{for(let i=0;i<800;i++){if(await fn())return;await new Promise(r=>setTimeout(r,25))}throw Error('Timed out: '+fn)};
const makeEditor=LabMarkdownEditor.create;window.editors=[];
LabMarkdownEditor.create=(parent,options)=>{const input=makeEditor(parent,options);editors.push(input);return input};
window.editor=()=>editors.find(input=>input.view.dom.isConnected);
window.ensureAsset=selector=>{let node=document.querySelector(selector);if(node?.closest('.objective-worktrees')&&document.querySelector('.objective-worktrees').hidden){document.querySelector('[data-fold-worktrees]').click();node=document.querySelector(selector);}if(node&&!node.getClientRects().length&&document.querySelector('[data-objectives-sidebar]')?.dataset.worktreeBrowse==='true'){const task=node.closest('.objective-task-worktrees')?.dataset.taskId;if(task)document.querySelector('.objective-sidebar-task [data-open-task="'+task+'"]').click();else{if(document.querySelector('.objective-worktrees').hidden)document.querySelector('[data-fold-worktrees]').click();document.querySelector('[data-fold-worktrees]').click();}node=document.querySelector(selector);}if(!node){LabObjectives.selectObjective(FIX.oid);node=document.querySelector(selector);}return node;};
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
const pasted=[],termXterm={paste:text=>pasted.push(text),focus(){},modes:{bracketedPasteMode:true}},termWS={readyState:1};
const _termDragState=null,workspaceTabsDragId=null;
const notices=[],opened=[],activated=[];let scopeRoot=FIX.folder;
window.LabExternalLinks={open:(url,options)=>{opened.push({url,options});return Promise.resolve(true)}};
window.explorerToast=(message,error)=>{if(error)throw Error(message);notices.push(message)};
document.getElementById('termBody').addEventListener('dragover',event=>event.preventDefault());
document.getElementById('termBody').addEventListener('drop',_termHandleDrop);
document.addEventListener('dragstart',event=>{if(event.isTrusted&&!window.allowTaskNativeDrag&&!event.target.closest('[data-drag-objective]')){window.nativeDrag={effect:event.dataTransfer.effectAllowed,reference:event.dataTransfer.getData('application/x-lab-reference')};event.preventDefault()}});
window.checkDrag=(selector,expected)=>{
 const references=Array.isArray(expected)?expected:[expected];
 const node=ensureAsset(selector),transfer=new DataTransfer();assert(node?.draggable,'draggable '+selector);
 node.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 assert(JSON.stringify(JSON.parse(transfer.getData('application/x-lab-reference')))===JSON.stringify(references),'captured references '+selector);
 const count=pasted.length;
 document.getElementById('termBody').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 const taskPayload=transfer.getData(LabTaskContext.mime);
 if(taskPayload){
   const model=JSON.parse(taskPayload),prompt=LabTaskContext.format(model);
   assert(pasted.length===count+1&&pasted.at(-1)===prompt&&prompt===transfer.getData('text/plain'),'unsent readable task prompt '+selector);
   assert(prompt.startsWith('Context:\nObjective: ')&&prompt.includes('This task: '+JSON.stringify(model.task.title))&&prompt.includes('Work only on This task: '),'task prompt separates background and current work');
   assert(prompt.includes('Task specification:')&&prompt.includes('read-only unless also listed under This task'),'task prompt labels specifications and limits inherited scope');
   assert(model.parents.every(p=>prompt.includes('Parent task: '+JSON.stringify(p.title))),'task prompt names every parent');
   assert(references.every(ref=>prompt.split('\n').filter(line=>line.endsWith(' — '+ref)).length===1),'task prompt includes each exact reference once');
 }else assert(pasted.length===count+1&&pasted.at(-1)===references.map(_termQuoteDropPath).join(' ')&&!pasted.at(-1).includes('\n'),'unsent console paste '+selector);
};
window.checkLink=async(selector,expected)=>{
 const node=ensureAsset(selector),transfer=new DataTransfer();
 node.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 const count=pasted.length;
 document.querySelector('#termSessionList .sess').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 await until(async()=>{const link=(await read()).terminal_links[FIX.session.session_id];return link&&Object.entries(expected).every(([key,value])=>JSON.stringify(link[key])===JSON.stringify(value))});
 assert(pasted.length===count,'association never writes terminal input');
 await LabObjectives.load(undefined,true);const browserCount=opened.filter(item=>item.url).length;assert(LabObjectives.openForTerminal(FIX.session),'linked terminal opens target');
 const target=(await read()).objectives[0].resources.find(r=>r.id===expected.resource_id);
 if(target?.kind==='link'){assert(document.querySelector('.objective-link-details')&&opened.filter(item=>item.url).length===browserCount,'linked terminal opens metadata without opening the URL');document.querySelector('[data-open-objective-link]').click();}
};
LabObjectives.connect({fileIcon:fileIconHtml,context:()=>({workspace_id:'demo',path:FIX.folder}),refreshTabs:()=>document.getElementById('tabs').innerHTML=LabObjectives.tabsHtml(FIX.folder),readyContent:()=>window.awaitAssets?.()||Promise.resolve(),prepareCenter:()=>{},scopeRoot:()=>scopeRoot,selectWorktree:row=>{scopeRoot=row.path},session:name=>name===FIX.session.name?FIX.session:null,sessions:()=>[FIX.session],activateLinkedTerminal:ids=>activated.push(ids),openLink:link=>opened.push({url:link.url}),openFile:file=>opened.push({file}),openNotebook:r=>opened.push({notebook:r.path}),openFolder:folder=>opened.push({folder})});
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
 async function click(selector,modifiers=0,button="left"){const p=await evaluate(`(async()=>{const n=ensureAsset(${JSON.stringify(selector)});assert(n,'click target '+${JSON.stringify(selector)});n.scrollIntoView({block:'center'});await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);const r=n.getBoundingClientRect(),p={x:r.x+r.width/2,y:r.y+r.height/2};assert(document.elementFromPoint(p.x,p.y)?.closest(${JSON.stringify(selector)})===n,'click target is hittable '+${JSON.stringify(selector)}+' '+JSON.stringify({point:p,rect:r.toJSON(),sidebar:document.getElementById('sidebar').getBoundingClientRect().toJSON(),center:document.getElementById('content').getBoundingClientRect().toJSON()})+' '+document.elementFromPoint(p.x,p.y)?.outerHTML.slice(0,300));return p})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button,clickCount:1,modifiers});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button,clickCount:1,modifiers});}
 async function type(text){await evaluate('editor().view.dispatch({selection:{anchor:editor().value.length},scrollIntoView:true});editor().focus()');await send('Input.insertText',{text});}
 await send('Emulation.setDeviceMetricsOverride',{width:1768,height:1100,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<200;i++){if(await evaluate('!!window.until'))break;await new Promise(r=>setTimeout(r,20));}
 await evaluate(`until(()=>document.getElementById('result').textContent==='READY')`);
 await evaluate(`(async()=>{
   const assets={marked:window.marked,DOMPurify:window.DOMPurify,LabMarkdownEditor:window.LabMarkdownEditor};
   const open=()=>ensureAsset('[data-objective-resource="'+FIX.rid+'"]').click();
   const unload=()=>{for(const key of Object.keys(assets))delete window[key]};
   const restore=()=>Object.assign(window,assets);
   unload();window.awaitAssets=()=>new Promise(resolve=>window.releaseAssets=()=>{restore();resolve()});
   open();await until(()=>window.releaseAssets);
   assert(document.querySelector('.objective-note-editor').textContent==='Loading document…','opening before lazy assets finish waits without calling Marked');
   LabObjectives.renderTasks();releaseAssets();await new Promise(resolve=>setTimeout(resolve,0));
   assert(!editor(),'a late asset load cannot mount an outgoing document');
   unload();window.awaitAssets=async()=>{throw Error('Could not load Markdown assets')};open();
   await until(()=>document.querySelector('.objective-document-status')?.textContent.includes('Could not load Markdown assets'));
   assert(!editor(),'asset failure is visible and does not create an editor');
   restore();delete window.awaitAssets;open();await until(()=>editor());
   assert(editor().value==='# Document\\n\\n**Bold** text.\\n','retry mounts the original body');
   assert(!contentErrors.length,'lazy document loading raises no unhandled errors: '+contentErrors.join('\\n'));
   LabObjectives.selectObjective(FIX.oid);
 })()`);
 await evaluate(`(async()=>{const d=await read(),o=d.objectives[0];for(const r of o.resources)checkDrag('[data-objective-resource="'+r.id+'"]',r.kind==='link'?r.url:(r.file_root||FIX.folder)+'/'+r.path);checkDrag('[data-open-objective-tasks]',o.manifest_path+'#view=tasks');checkDrag('[data-select-worktree="workspace-root"]',FIX.folder);checkDrag('[data-select-worktree="objective-root"]',o.path);checkDrag('[data-objective-worktree] [data-select-worktree]',FIX.checkout);const result=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'task',objective_id:FIX.oid,title:'Task with details'}})});assert(result.ok,'task creation');await until(()=>document.querySelector('[data-open-task]'));assert(document.querySelector('.objective-task-title').textContent==='Task with details','external task appears automatically');const updated=await read(),task=updated.objectives[0].tasks[0],resource=updated.objectives[0].resources.find(r=>r.id===task.document_id);checkDrag('[data-open-objective-tasks]',FIX.folder+'/'+resource.path)})()`);
 const dragPoint=await evaluate(`(()=>{const n=document.querySelector('[data-objective-resource]');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+Math.min(40,r.width/2),y:r.y+r.height/2}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...dragPoint});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...dragPoint,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:dragPoint.x+20,y:dragPoint.y+4,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:dragPoint.x+40,y:dragPoint.y+8,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:dragPoint.x+40,y:dragPoint.y+8,button:'left',clickCount:1});
 await evaluate(`assert(nativeDrag.effect==='copyLink'&&JSON.parse(nativeDrag.reference)[0]===FIX.folder+'/'+FIX.editorPath,'trusted native drag carries source and supports copy or association')`);
 await evaluate(`(async()=>{for(const r of (await read()).objectives[0].resources)await checkLink('[data-objective-resource="'+r.id+'"]',{resource_id:r.id});assert(opened.some(o=>o.url==='https://example.com/a?one=1&two=2#section')&&opened.some(o=>o.notebook)&&opened.some(o=>o.file),'links, notebooks and files reopen');await checkLink('[data-open-objective-tasks]',{view:'tasks'});assert(document.querySelector('.objective-working h2').textContent==='Tasks','Tasks association opens task list');for(const [id,root] of [['workspace-root',FIX.folder],['objective-root',(await read()).objectives[0].path]]){await checkLink('[data-select-worktree="'+id+'"]',{folder:{root,path:'.'}});assert(document.querySelector('#content .objective-task-list'),'whole folder association opens task assignment view');assert(scopeRoot===root,'folder association selects sidebar scope')}await checkLink('[data-objective-worktree] [data-select-worktree]',{folder:{root:FIX.checkout,path:'.'}});assert(document.querySelector('#content .objective-task-list'),'worktree association opens task assignment view');assert(scopeRoot===FIX.checkout,'worktree association selects captured checkout');const transfer=new DataTransfer();transfer.setData('application/x-lab-file-path',JSON.stringify([FIX.folder+'/existing file.py']));transfer.setData('application/x-lab-file-context',JSON.stringify({kind:'file',root:FIX.folder,path:'existing file.py'}));document.querySelector('#termSessionList .sess').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await until(async()=>{const link=(await read()).terminal_links[FIX.session.session_id];return link.file?.root===FIX.folder&&link.file.path==='existing file.py'});assert(pasted.every(p=>!p.includes('\\n')),'no submitted drops')})()`);
 await click('[data-objective-resource]');
 await evaluate(`checkDrag('[data-objective-tab="'+FIX.child+'"]',FIX.folder+'/'+FIX.editorPath+'#tab='+FIX.child)`);
 await evaluate(`checkLink('[data-objective-tab="'+FIX.child+'"]',{resource_id:FIX.rid,tab_id:FIX.child})`);
 await click('[data-objective-resource]');
 await evaluate(`assert(!document.querySelector('[data-objective-bucket=unassigned]'),'unassigned hidden outside the Objective overview');assert(editor()&&document.querySelector('.cm-content strong')?.textContent==='Bold','live editor on open');assert(getComputedStyle(editor().view.dom).fontSize==='13px','native text size');assert(JSON.stringify([...document.querySelectorAll('[data-objectives-sidebar]>[data-objective-bucket]')].map(n=>n.dataset.objectiveBucket))===JSON.stringify(['objective','tasks','task']),'pinned assets above tasks; unassigned hidden while editing');assert(document.querySelector('.objective-sidebar-task [data-open-task]')&&!document.querySelector('.objective-sidebar-task input'),'left tasks navigate without edits');assert([...document.querySelectorAll('.objective-sidebar-task')].every(n=>n.firstElementChild.classList.contains('objective-sidebar-task-status')&&n.lastElementChild.hasAttribute('data-task-icon')),'status left and terminal icon right');assert(document.querySelectorAll('.objective-worktrees [data-objective-root]').length===2&&document.querySelector('.objective-worktrees [data-objective-worktree]'),'fixed roots and every worktree stay in scope navigation');assert(!document.querySelector('[data-objective-bucket=unassigned] [data-objective-worktree]'),'unassociated worktree stays hidden outside the overview');assert(document.querySelectorAll('.repo-tabs .objective-tab').length===2&&document.querySelector('[data-all-objectives]').textContent==='Objectives','Objectives and one current tab');assert(!document.querySelector('.objective-selectors'),'no duplicate sidebar selectors');assert(document.querySelectorAll('.objective-document [role=tablist]').length===0,'tabs outside content')`);
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
 await evaluate(`LabObjectives.change({type:'asset-star',objective_id:FIX.oid,resource_id:FIX.rid,starred:false})`);
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
 const points=await evaluate(`(()=>{const source=document.querySelector('.objective-library-row[data-drag-objective="'+FIX.oid+'"]'),target=document.querySelector('[data-objective-slot="0"]');const a=source.getBoundingClientRect(),b=target.getBoundingClientRect();assert(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)?.closest('[data-objective-slot]')===target,'visible native drop target '+JSON.stringify({a,b}));return{source:{x:a.x+20,y:a.y+a.height/2},target:{x:b.x+b.width/2,y:b.y+b.height/2}}})()`);
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
 await evaluate(`assert(document.querySelector('.objective-overview')&&!document.querySelector('.objective-switch-menu'),'hover choice switches objective and closes menu');assert(document.querySelector('[data-current-objective]').style.getPropertyValue('--vault-color')==='#bc8cff','selected second slot color')`);
 await evaluate(`document.getElementById('sidebar').style.display='';LabObjectives.selectObjective(FIX.oid)`);
 const linkId=await evaluate(`(async()=>{const d=await read();return d.objectives[0].resources.find(r=>r.kind==='link').id})()`);
 await evaluate(`LabObjectives.change({type:'asset-star',objective_id:FIX.oid,resource_id:'${linkId}',starred:true})`);
 const linkSelector='[data-objectives-sidebar] [data-objective-resource="'+linkId+'"]';
 await click(linkSelector);
 await evaluate(`assert(document.querySelector('.objective-overview'),'single link click preserves center');assert(opened.at(-1).url==='https://example.com/a?one=1&two=2#section'&&opened.at(-1).options.clientOnly,'single click opens actual URL in clicking browser')`);
 await click(linkSelector,4);
 await evaluate(`assert(document.querySelector('.objective-link-details')&&!document.querySelector('#content iframe'),'Cmd clicks show link details');assert(document.querySelector('[data-objective-link-field="url"]').value==='https://example.com/a?one=1&two=2#section','stored URL is editable')`);
 async function fill(selector,text){await click(selector);await evaluate(`document.querySelector(${JSON.stringify(selector)}).select()`);await send('Input.insertText',{text});}
 await fill('[data-objective-link-field="title"]','Updated reference');
 await fill('[data-objective-link-field="url"]','https://example.com/updated?tab=main');
 await fill('[data-objective-link-field="tldr"]','Why this link matters.');
 await click('[data-add-link-property]');
 await fill('.objective-link-property:last-child [data-link-property-name]','Status');
 await fill('.objective-link-property:last-child [data-link-property-value]','In review');
 await evaluate(`LabObjectives.renderTasks()`);await click(linkSelector,4);
 await evaluate(`assert(document.querySelector('[data-objective-link-field="tldr"]').value==='Why this link matters.'&&document.querySelector('.objective-link-property:last-child [data-link-property-value]').value==='In review','navigation retains unsaved link fields and properties')`);
 await click('[data-open-objective-link]');
 await evaluate(`assert(opened.at(-1).url==='https://example.com/updated?tab=main','Open uses the valid edited URL')`);
 await click('[data-save-objective-link]');
 await evaluate(`(async()=>{await until(async()=>{const r=(await read()).objectives[0].resources.find(r=>r.id==='${linkId}');return r.title==='Updated reference'&&r.tldr==='Why this link matters.'});const r=(await read()).objectives[0].resources.find(r=>r.id==='${linkId}');assert(r.metadata.Status==='In review'&&r.metadata.Count===3&&JSON.stringify(r.metadata.Tags)==='["a","b"]','editable properties preserve unchanged JSON metadata');assert(document.querySelector('[data-link-details-title]').textContent==='Updated reference','saved title rendered')})()`);
 await evaluate(`LabObjectives.renderTasks()`);
 await click(linkSelector);
 await evaluate(`assert(document.querySelector('.objective-working h2').textContent==='Tasks','single click leaves center unchanged');assert(opened.at(-1).url==='https://example.com/updated?tab=main'&&opened.at(-1).options.clientOnly,'single click opens saved URL directly');window.beforeMetadataOpen=opened.length`);
 await click(linkSelector,4);
 await evaluate(`assert(opened.length===beforeMetadataOpen,'Cmd click opens metadata without visiting URL')`);
 await click('[data-add-objective-sublink]');
 await fill('.objective-dialog [name=title]','Overview tab');
 await fill('.objective-dialog [name=url]','https://example.com/updated?tab=overview');
 await click('.objective-dialog [type=submit]');
 const subId=await evaluate(`(async()=>{await until(async()=>!!(await read()).objectives[0].resources.find(r=>r.id==='${linkId}').sublinks?.length);return (await read()).objectives[0].resources.find(r=>r.id==='${linkId}').sublinks[0].id})()`);
 const parentHover=await evaluate(`(()=>{const n=document.querySelector('${linkSelector}');n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...parentHover});
 await new Promise(r=>setTimeout(r,500));
 await evaluate(`assert(!document.querySelector('[data-objectives-sidebar] [data-objective-sublink]'),'sublinks wait for one-second hover')`);
 await evaluate(`until(()=>document.querySelector('[data-objectives-sidebar] [data-objective-sublink]'))`);
 const childSelector='[data-objectives-sidebar] [data-objective-sublink="'+subId+'"]';
 await click(childSelector);
 await evaluate(`assert(opened.at(-1).url==='https://example.com/updated?tab=overview'&&document.querySelector('[data-link-details-title]').textContent==='Updated reference','single child click opens exact destination and preserves metadata');window.beforeChildMetadata=opened.length`);
 await click(childSelector,4);
 await evaluate(`assert(opened.length===beforeChildMetadata,'Cmd child click does not visit URL');assert(document.querySelector('[data-link-details-title]').textContent==='Overview tab'&&document.querySelector('[data-objective-link-field="url"]').value==='https://example.com/updated?tab=overview','child opens its own details')`);
 await fill('[data-objective-link-field="tldr"]','Tab-specific context');await click('[data-save-objective-link]');
 await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].resources.find(r=>r.id==='${linkId}').sublinks[0].tldr==='Tab-specific context');checkDrag('${childSelector}','https://example.com/updated?tab=overview');await checkLink('${childSelector}',{resource_id:'${linkId}',sub_link_id:'${subId}'});assert(document.querySelector('[data-link-details-title]').textContent==='Overview tab','terminal target reopens exact sublink')})()`);
 await fill('[data-objective-link-field="url"]','javascript:alert(1)');await click('[data-save-objective-link]');
 await evaluate(`assert(document.querySelector('[data-link-details-status]').textContent.includes('http or https')&&document.querySelector('[data-objective-link-field="url"]').value==='javascript:alert(1)','invalid URL retains draft and shows error');assert(document.querySelector('[data-open-objective-link]').disabled,'unsafe draft cannot be opened')`);
 await click('[data-revert-objective-link]');
 await evaluate(`until(()=>document.querySelector('[data-objective-link-field="url"]').value==='https://example.com/updated?tab=overview')`);
 await click('[data-open-parent-link]');
 await fill('[data-objective-link-field="tldr"]','Retained conflicting link draft');
 await evaluate(`(async()=>{const d=await read();const r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'link-update',objective_id:FIX.oid,resource_id:'${linkId}',tldr:'Concurrent summary',sublinks:[{title:'Fresh external sublink',url:'https://example.com/fresh'}]}})});assert(r.ok,'concurrent link edit');await until(()=>document.querySelector('[data-link-children]').textContent.includes('Fresh external sublink'));assert(document.querySelector('[data-objective-link-field="tldr"]').value==='Retained conflicting link draft','poll preserves unsaved link edits')})()`);
 await click('[data-save-objective-link]');
 await evaluate(`until(()=>document.querySelector('[data-link-details-status]').textContent.includes('changed elsewhere'));assert(document.querySelector('[data-objective-link-field="tldr"]').value==='Retained conflicting link draft','poll and conflict keep link draft')`);
 await click('[data-revert-objective-link]');
 await evaluate(`until(()=>document.querySelector('[data-objective-link-field="tldr"]').value==='Concurrent summary')`);
 await evaluate(`LabObjectives.change({type:'asset-star',objective_id:FIX.oid,resource_id:'${linkId}',starred:false})`);
 await evaluate(`document.getElementById('sidebar').classList.add('sidebar');document.getElementById('content').classList.add('main');window.scrollTo(0,0);LabObjectives.selectObjective(FIX.oid);window.allowTaskNativeDrag=true;window.taskId=document.querySelector('.objective-task-row').dataset.taskId;assert(document.querySelector('.objective-task-title').tagName==='A'&&document.querySelector('.objective-task-title').href.includes('objective_task='),'task title is a real document hyperlink')`);
 const notebookId=await evaluate(`(async()=>{const d=await read();return d.objectives[0].resources.find(r=>r.kind==='notebook').id})()`);
 const assetPoints=await evaluate(`(()=>{const source=document.querySelector('[data-objective-resource="${notebookId}"]'),target=document.querySelector('.objective-task-row');source.scrollIntoView({block:'center'});target.scrollIntoView({block:'center'});const a=source.getBoundingClientRect(),b=target.getBoundingClientRect(),p={x:a.x+20,y:a.y+a.height/2};assert(document.elementFromPoint(p.x,p.y)?.closest('[data-objective-resource]')===source,'visible native asset source');return{source:p,target:{x:b.x+b.width/2,y:b.y+b.height/2}}})()`);
 dragData=null;await send('Input.setInterceptDrags',{enabled:true});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...assetPoints.source});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...assetPoints.source,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:assetPoints.source.x+25,y:assetPoints.source.y,button:'left',buttons:1});
 for(let i=0;i<100&&!dragData;i++)await new Promise(r=>setTimeout(r,20));
 if(!dragData?.items.some(item=>item.mimeType==='application/x-lab-objective-resource'))throw Error('Native task asset drag payload');
 for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...assetPoints.target,data:dragData});
 await send('Input.setInterceptDrags',{enabled:false});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...assetPoints.target,button:'left',clickCount:1});
 await evaluate(`until(async()=>(await read()).objectives[0].tasks[0].assets?.some(a=>a.resource_id==='${notebookId}'))`);
 await evaluate(`(async()=>{
   const source=document.querySelector('[data-objective-resource="'+FIX.rid+'"]'),transfer=new DataTransfer();source.dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
   await until(async()=>(await read()).objectives[0].tasks[0].assets?.length===2);await LabObjectives.load(undefined,true);
   const file=new DataTransfer();file.setData('application/x-lab-file-path',JSON.stringify([FIX.folder+'/query.sql']));file.setData('application/x-lab-file-context',JSON.stringify({kind:'file',root:FIX.folder,path:'query.sql'}));document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:file}));
   await until(async()=>(await read()).objectives[0].tasks[0].assets?.length===3);await LabObjectives.load(undefined,true);
   const folder=new DataTransfer();folder.setData('application/x-lab-file-path',JSON.stringify([FIX.folder]));folder.setData('application/x-lab-file-context',JSON.stringify({kind:'folder',root:FIX.folder,path:'.'}));document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:folder}));
   await until(async()=>(await read()).objectives[0].tasks[0].assets?.length===4);await LabObjectives.load(undefined,true);
   const worktreeTransfer=new DataTransfer();document.querySelector('[data-objective-worktree] [data-select-worktree]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:worktreeTransfer}));document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:worktreeTransfer}));
   await until(async()=>(await read()).objectives[0].tasks[0].assets?.length===5);await LabObjectives.load(undefined,true);
   const url=new DataTransfer();url.setData('text/uri-list','https://example.com/task-evidence');document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:url}));
   await until(async()=>(await read()).objectives[0].tasks[0].assets?.length===6);await LabObjectives.load(undefined,true);
   const native=document.createElement('section');native.dataset.projectDirectory='.';native.innerHTML='<a data-open-file data-filepath="query.sql" data-entry-root="'+FIX.folder+'">query.sql</a>';document.getElementById('sidebar').append(native);
   window.resourceOrder=[...document.querySelectorAll('[data-objectives-sidebar] .objective-resource')].map(n=>n.dataset.objectiveResource);
   const d=await read();window.nbAsset=d.objectives[0].tasks[0].assets.find(a=>a.resource_id==='${notebookId}').id;
 })()`);
 await click('.objective-task-row [data-task-assets]');
 await evaluate(`assert(!document.querySelector('[data-pick-task-icon]'),'asset list cannot override task icons on click')`);
 await click('.objective-dialog [type=submit]');await click('.objective-task-title');
 await evaluate(`assert(document.querySelector('.objective-sidebar-task [data-task-icon]')?.childElementCount===0&&document.querySelector('[data-current-objective] .objective-task-default-icon')?.textContent==='⬜','ordinary attachments leave the right task icon empty and retain the tab status icon')`);
 await click('.objective-sidebar-task .objective-sidebar-task-title',0,'right');
 await evaluate(`assert(document.querySelectorAll('.objective-task-status-menu [role=menuitemradio]').length===5&&document.querySelector('.objective-task-status-menu [aria-checked=true]').dataset.setTaskStatus==='todo','secondary click shows all statuses without navigating');assert(document.querySelector('.objective-task-mode-head'),'secondary click retains task view')`);
 await click('.objective-task-status-menu [data-set-task-status=in_progress]');
 await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].tasks[0].status==='in_progress');await LabObjectives.load(undefined,true);assert(document.querySelector('.objective-sidebar-task-status').textContent==='🟡'&&document.querySelector('[data-current-objective] .objective-task-default-icon').textContent==='🟡','in progress survives reload with matching default icons');assert(!document.querySelector('[data-task-done]').checked&&!document.querySelector('.objective-task-status-menu'),'in progress is unfinished and closes menu')})()`);
 await click('.objective-sidebar-task .objective-sidebar-task-title',0,'right');

 for(const [status,icon] of [['paused','⏸'],['wont_do','🚫']]){
  await click('.objective-task-status-menu [data-set-task-status='+status+']');
  await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].tasks[0].status==='${status}');await LabObjectives.load(undefined,true);assert(document.querySelector('.objective-sidebar-task-status').textContent==='${icon}'&&!document.querySelector('[data-task-done]').checked,'paused and declined statuses persist without completing the task')})()`);
  await click('.objective-sidebar-task .objective-sidebar-task-title',0,'right');
 }
 await click('.objective-task-status-menu [data-set-task-status=done]');
 await evaluate(`until(async()=>(await read()).objectives[0].tasks[0].done)`);
 await evaluate(`assert(document.querySelector('.objective-sidebar-task-status').textContent==='✅'&&document.querySelector('[data-task-done]').checked,'completed updates status and completion control')`);
 await click('.objective-sidebar-task .objective-sidebar-task-title',0,'right');
 await click('.objective-task-status-menu [data-set-task-status=todo]');
 await evaluate(`until(async()=>(await read()).objectives[0].tasks[0].status==='todo')`);
 await evaluate(`assert(document.querySelector('.objective-sidebar-task-status').textContent==='⬜'&&getComputedStyle(document.querySelector('.objective-sidebar-task-status')).boxShadow!=='none','undo retains box with red frame')`);
 await evaluate(`document.querySelector('.objective-sidebar-task-title').focus()`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'F10',code:'F10',modifiers:8,windowsVirtualKeyCode:121});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'F10',code:'F10',modifiers:8,windowsVirtualKeyCode:121});
 await evaluate(`assert(document.querySelector('.objective-task-status-menu'),'keyboard context menu')`);
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await evaluate(`assert(!document.querySelector('.objective-task-status-menu')&&document.activeElement.matches('.objective-sidebar-task-title'),'escape closes menu and returns focus')`);
 const iconPoints=await evaluate(`(()=>{const source=document.querySelector('[data-objective-bucket=task] [data-objective-resource="${notebookId}"]'),target=document.querySelector('.objective-sidebar-task [data-task-icon]');source.scrollIntoView({block:'nearest'});target.scrollIntoView({block:'nearest'});const a=source.getBoundingClientRect(),b=target.getBoundingClientRect();return{source:{x:a.x+20,y:a.y+a.height/2},target:{x:b.x+b.width/2,y:b.y+b.height/2}}})()`);
 dragData=null;await send('Input.setInterceptDrags',{enabled:true});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...iconPoints.source});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...iconPoints.source,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:iconPoints.source.x+25,y:iconPoints.source.y,button:'left',buttons:1});
 for(let i=0;i<100&&!dragData;i++)await new Promise(r=>setTimeout(r,20));
 if(!dragData?.items.some(item=>item.mimeType==='application/x-lab-objective-resource'))throw Error('Native task icon drag payload');
 for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...iconPoints.target,data:dragData});
 await send('Input.setInterceptDrags',{enabled:false});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...iconPoints.target,button:'left',clickCount:1});
 await evaluate(`until(async()=>(await read()).objectives[0].tasks[0].icon_asset_id===nbAsset)`);
 await evaluate(`assert(!editor()&&document.querySelector('.objective-document-preview').textContent.includes('Describe the outcome'),'task click opens its linked details read only');assert(!!document.querySelector('[data-task-mode-head]'),'task click opens its working header');assert(document.querySelectorAll('[data-objective-bucket=task] .objective-resources > *').length===6&&document.querySelector('.objective-sidebar-task.active'),'selected task shows required details and attached assets beneath task list');assert(document.querySelector('.objective-task-worktrees [data-objective-worktree]')&&!document.querySelector('[data-objective-bucket=unassigned] [data-objective-worktree]'),'assigned worktree moves from Unassigned into the task Worktrees section');assert(!document.querySelector('[data-project-directory] .objective-star,[data-native-asset-tools]'),'explorer files never receive asset stars');window.bucketOrder=[...document.querySelectorAll('[data-objectives-sidebar] .objective-resource')].map(n=>n.dataset.objectiveResource);assert(document.querySelector('.objective-task-mode-head [data-task-done]').disabled,'view mode locks completion');assert(getComputedStyle(document.querySelector('[data-project-directory]')).display!=='none','task selection keeps native Files visible');assert(document.querySelector('[data-current-objective] .ft-nb'),'current tab inherits notebook task icon')`);
 await evaluate(`(async()=>{const d=await read(),o=d.objectives[0],t=o.tasks[0],r=o.resources.find(r=>r.id===t.document_id);const refs=[FIX.folder+'/'+r.path+'#tab='+t.tab_id,...t.assets.map(a=>{if(a.folder)return a.folder.root+(a.folder.path==='.'?'':'/'+a.folder.path);const asset=o.resources.find(r=>r.id===a.resource_id);return asset.kind==='link'?asset.url:(asset.file_root||FIX.folder)+'/'+asset.path})];checkDrag('[data-open-task]',refs);assert(refs.includes('https://example.com/task-evidence')&&refs.includes(FIX.checkout)&&refs.some(ref=>ref.endsWith('Analysis.ipynb')),'task agent bundle includes links, worktree and notebook references');await checkLink('[data-open-task]',{task_id:t.id});assert(!editor()&&document.querySelector('.objective-document-preview')&&!!document.querySelector('[data-task-mode-head]'),'task terminal association opens read-only details')})()`);
 await evaluate(`assert(!document.querySelector('[data-task-focus-mode],[aria-label="Task focus mode"]')&&!document.querySelector('.objective-task-asset-highlight'),'focus options and highlights removed');assert(JSON.stringify([...document.querySelectorAll('[data-objectives-sidebar] .objective-resource')].map(n=>n.dataset.objectiveResource))===JSON.stringify(bucketOrder),'removing focus controls preserves asset order');assert(document.querySelectorAll('[data-close-objective-task]').length===1,'task close remains available')`);
 await click('.objective-document-preview');
 await evaluate(`assert(!editor()&&document.querySelector('[data-task-document-mode=view]').getAttribute('aria-pressed')==='true','ordinary Markdown click stays in View')`);
 await click('.objective-document-preview',4);
 await evaluate(`(async()=>{await until(()=>editor());assert(document.querySelector('[data-task-document-mode=edit]').getAttribute('aria-pressed')==='true','Command-click enables Edit')})()`);
 await type(' Command-click keeps this draft.');
 await click('.objective-document .cm-content',4);
 await evaluate(`(async()=>{assert(!editor()&&document.querySelector('.objective-document-preview').textContent.includes('Command-click keeps this draft.'),'Command-click returns to View and preserves unsaved text');assert(document.querySelector('[data-task-document-mode=view]').getAttribute('aria-pressed')==='true'&&document.querySelector('[data-task-done]').disabled,'shortcut restores read-only controls');await until(async()=>{const o=(await read()).objectives[0];return o.resources.find(r=>r.id===o.tasks[0].document_id).content.tabs.some(t=>t.body.includes('Command-click keeps this draft.'))})})()`);
 await click('.objective-document-preview',4);
 await evaluate(`assert(editor().value.includes('Command-click keeps this draft.'),'editing again restores the same Markdown');document.querySelector('.objective-document .cm-content').dispatchEvent(new MouseEvent('click',{bubbles:true,ctrlKey:true,button:0}));assert(!editor(),'Ctrl-click offers the same shortcut');assert(!contentErrors.length,'mode shortcut raises no editor errors')`);
 await click('[data-close-objective-task]');
 await evaluate(`assert(document.querySelector('.objective-working h2').textContent==='Tasks'&&!document.querySelector('[data-close-objective-task]')&&!document.querySelector('.objective-task-focus'),'red corner close exits task mode');assert(document.activeElement.matches('[data-open-task]')&&getComputedStyle(document.querySelector('[data-project-directory]')).display!=='none','close restores task focus and complete sidebar');assert(!document.querySelector('[data-current-objective] .objective-task-tab-icon'),'current tab returns to objective')`);
 await click('.objective-task-title');
 await evaluate(`(()=>{const button=document.querySelector('[data-close-objective-task]'),box=button.getBoundingClientRect(),center=document.getElementById('content').getBoundingClientRect(),rename=document.querySelector('[data-rename-objective-resource]').getBoundingClientRect(),red=document.createElement('span');red.style.color='var(--red)';document.body.append(red);assert(button.getAttribute('aria-label')==='Close task mode'&&getComputedStyle(button).color===getComputedStyle(red).color,'task close is accessible and red');red.remove();assert(box.right<=center.right&&box.right>=center.right-20&&box.top>=center.top&&rename.right<box.left,'close sits in top-right corner without overlapping Rename')})()`);
 await click('[data-task-document-mode=edit]');
 await type(' Close preserves this task draft.');
 await click('[data-close-objective-task]');
 await evaluate(`until(async()=>{const o=(await read()).objectives[0];return o.resources.find(r=>r.id===o.tasks[0].document_id).content.tabs.some(t=>t.body.includes('Close preserves this task draft.'))})`);
 await click('.objective-task-title');
 await evaluate(`assert(!editor()&&document.querySelector('.objective-document-preview').textContent.includes('Close preserves this task draft.'),'close saved task draft and reopens in View');document.getElementById('content').innerHTML='<div class="nb-notebook-header">Native notebook view</div>'`);
 await evaluate(`until(()=>document.querySelector('[data-close-objective-task]'));assert(document.querySelectorAll('[data-close-objective-task]').length===1,'native center replacement retains exactly one task close')`);
 await evaluate(`(()=>{const style=document.createElement('style');style.id='native-sticky-fixture';style.textContent='#tabs{position:fixed;top:0;left:0;right:0;height:36px;z-index:80;background:var(--bg-primary)}.nb-jump-controls{position:fixed;top:36px;left:0;right:0;height:41px;z-index:79;background:var(--bg-primary)}#content{min-height:1800px}';document.head.append(style);document.getElementById('content').insertAdjacentHTML('afterbegin','<nav class="nb-jump-controls" aria-label="Notebook controls">Native fixed notebook toolbar</nav>');window.scrollTo(0,400)})()`);
 await evaluate(`until(()=>{const b=document.querySelector('[data-close-objective-task]'),r=b.getBoundingClientRect();return r.top>=document.querySelector('#tabs').getBoundingClientRect().bottom&&document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('[data-close-objective-task]')===b})`);
 await click('[data-close-objective-task]');
 await evaluate(`assert(document.querySelector('.objective-working h2').textContent==='Tasks'&&!document.querySelector('[data-close-objective-task]'),'scrolled native notebook close is clickable above its fixed toolbar');document.getElementById('native-sticky-fixture').remove();window.scrollTo(0,0)`);
 await evaluate(`(async()=>{await checkLink('[data-objective-resource="${linkId}"]',{resource_id:'${linkId}'});LabObjectives.renderTasks();const transfer=new DataTransfer();transfer.setData('application/x-lab-terminal',FIX.session.name);const count=pasted.length,before=await read();document.querySelector('.objective-task-row').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await new Promise(r=>setTimeout(r,50));assert((await read()).revision===before.revision,'middle task rows reject terminal association');document.querySelector('.objective-sidebar-task').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await until(async()=>(await read()).terminal_links[FIX.session.session_id].task_id===taskId);assert(pasted.length===count,'left reverse terminal drop links task without input');const d=await read();assert(LabObjectives.taskForTerminal(FIX.session).icon.includes('ft-nb'),'terminal task metadata inherits the selected notebook asset icon');assert(d.objectives[0].resources.find(r=>r.id==='${notebookId}').worktree===null,'asset attachment preserves resource ownership and scope');assert(!contentErrors.length,'task focus raises no browser errors: '+contentErrors.join('\\n'))})()`);
 await evaluate(`(async()=>{const saved=(await realFetch('/api/term/sessions/saved?workspace_id=demo').then(r=>r.json()))[0],d=await read(),task=d.objectives[0].tasks.find(t=>t.id===taskId);assert(saved.label===task.title,'terminal drop persists the task name');for(const field of ['session_id','name','cwd','agent_session_id'])assert(saved[field]===FIX.session[field],'task naming preserves '+field)})()`);
 await click('.objective-sidebar-task [data-open-task]');
 await evaluate(`LabObjectives.change({type:'asset-star',objective_id:FIX.oid,resource_id:'${linkId}',starred:false})`);
 await click(`[data-objective-bucket=task] [data-resource-group="${notebookId}"] [data-objective-star]`);
 await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].shared_assets.some(a=>a.resource_id==='${notebookId}'));await until(()=>document.querySelector('[data-objective-bucket=objective] [data-objective-resource="${notebookId}"]')&&document.querySelector('[data-objective-bucket=task] [data-objective-resource="${notebookId}"]'));assert(document.querySelector('[data-objective-bucket=task] [data-objective-resource="${notebookId}"]'),'starring preserves task membership while adding shared context')})()`);
 await click(`[data-objective-bucket=objective] [data-resource-group="${notebookId}"] [data-objective-star]`);
 await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].shared_assets.length===0);await until(()=>!document.querySelector('[data-objective-bucket=objective] [data-objective-resource="${notebookId}"]'));assert(document.querySelector('[data-objective-bucket=task] [data-objective-resource="${notebookId}"]'),'unstarring retains task asset')})()`);
 await click(`[data-objective-bucket=unassigned] [data-resource-group="${linkId}"] [data-objective-star]`);
 await evaluate(`until(async()=>(await read()).objectives[0].shared_assets.some(a=>a.resource_id==='${linkId}'))`);
 await evaluate(`(async()=>{const act=async fields=>{const d=await read(),r=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{objective_id:FIX.oid,...fields}})});assert(r.ok,'task tree fixture');return r.json()};let d=await act({type:'task',title:'Inspect inherited evidence',parent_id:taskId});window.childTaskId=d.objectives[0].tasks[0].children[0].id;await act({type:'task',title:'Second evidence check',parent_id:taskId});d=await act({type:'task',title:'Independent review'});window.secondTaskId=d.objectives[0].tasks[1].id;await act({type:'task',title:'Independent child',parent_id:secondTaskId});await LabObjectives.load(undefined,true);window.taskAssetsPosition=()=>document.querySelector('[data-objective-bucket=task]').getBoundingClientRect().top+document.getElementById('sidebar').scrollTop+window.scrollY;LabObjectives.renderTasks();window.reservedAssetsTop=taskAssetsPosition()})()`);
 await click('.objective-sidebar-task [data-open-task]');
 await evaluate(`assert(Math.abs(taskAssetsPosition()-reservedAssetsTop)<1,'assets stay put when largest task unfolds');assert(document.querySelectorAll('.objective-sidebar-task.child').length===2&&!document.querySelector('.objective-sidebar-task input'),'only the active parent expands with navigation-only rows')`);
 const otherTask=await evaluate(`'.objective-sidebar-task [data-open-task="'+secondTaskId+'"]'`);await click(otherTask);
 await evaluate(`assert(Math.abs(taskAssetsPosition()-reservedAssetsTop)<1,'assets stay put when a smaller task unfolds');assert(document.querySelectorAll('.objective-sidebar-task.child').length===1&&!document.querySelector('.objective-sidebar-task [data-open-task="'+childTaskId+'"]'),'selecting another task folds the previous parent')`);
 await click('[data-show-unassigned]');
 await evaluate(`assert(document.querySelector('[data-objective-overview-mode]').value==='unassigned'&&!document.querySelector('[data-task-mode-head]'),'Unassigned opens the review view')`);
 const copiedId=await evaluate(`(async()=>{const o=(await read()).objectives[0];return o.resources.find(r=>r.path==='copied.ipynb').id})()`);
 await evaluate(`(()=>{const transfer=new DataTransfer();document.querySelector('[data-objective-resource="${copiedId}"]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));document.querySelector('.objective-sidebar-task [data-task-icon="'+secondTaskId+'"]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}))})()`);
 await evaluate(`(async()=>{await until(async()=>{const o=(await read()).objectives[0],t=o.tasks[1],a=t.assets?.find(a=>a.resource_id==='${copiedId}');return a&&t.icon_asset_id===a.id});await until(()=>document.querySelector('.objective-sidebar-task [data-task-icon="'+secondTaskId+'"] .ft-nb'));assert(document.querySelector('.objective-sidebar-task [data-task-icon="'+secondTaskId+'"] .ft-nb'),'asset icon drop attaches and chooses a file-extension icon');window.reservedAssetsTop=taskAssetsPosition()})()`);
 await click('.objective-sidebar-task [data-open-task]');
 const subtaskSelector=await evaluate(`'.objective-sidebar-task [data-open-task="'+childTaskId+'"]'`);await click(subtaskSelector);
 await evaluate(`(async()=>{const o=(await read()).objectives[0],p=o.tasks[0],c=p.children[0],r=o.resources.find(r=>r.id===p.document_id);const refs=[o.resources.find(r=>r.id==='${linkId}').url,FIX.folder+'/'+r.path+'#tab='+p.tab_id,...p.assets.map(a=>{if(a.folder)return a.folder.root+(a.folder.path==='.'?'':'/'+a.folder.path);const r=o.resources.find(r=>r.id===a.resource_id);return r.kind==='link'?r.url:(r.file_root||FIX.folder)+'/'+r.path}),FIX.folder+'/'+r.path+'#tab='+c.tab_id];checkDrag('.objective-sidebar-task [data-open-task="'+childTaskId+'"]',[...new Set(refs)]);assert(document.querySelector('[data-task-mode-head] a[data-open-task]').textContent==='Inspect inherited evidence','subtask mode shows selected name');assert(Math.abs(taskAssetsPosition()-reservedAssetsTop)<1,'assets stay put on child navigation');})()`);
 await click('[data-task-document-mode=edit]');
 await click('[data-task-mode-head] [data-task-done]');
 await evaluate(`(async()=>{await until(async()=>(await read()).objectives[0].tasks[0].children[0].done);assert(!document.querySelector('.objective-sidebar-task input'),'completion remains owned by working-area task header')})()`);
 await click('[data-close-objective-task]');
 await evaluate(`assert(!document.querySelector('[data-objective-bucket=task] [data-objective-resource]')&&!document.querySelector('.objective-sidebar-task.child'),'closing task clears assets and expansion');assert(Math.abs(taskAssetsPosition()-reservedAssetsTop)<1,'assets stay put after closing task mode');assert(!contentErrors.length,'new live task buckets raise no browser errors: '+contentErrors.join('\\n'))`);
 await click('.objective-sidebar-task [data-open-task]');
 await click('.objective-task-worktrees [data-objective-worktree] [data-objective-star]');
 await evaluate(`(async()=>{await until(()=>document.querySelector('[data-objective-bucket=objective] [data-objective-worktree]'));assert(document.querySelector('.objective-task-worktrees [data-objective-worktree]'),'starring a worktree preserves its task attachment')})()`);
 await click(otherTask);
 await evaluate(`(async()=>{await until(()=>document.querySelector('.objective-sidebar-task.active')?.dataset.taskId===secondTaskId);assert(document.querySelector('[data-objective-bucket=objective] [data-objective-worktree]')&&!document.querySelector('.objective-task-worktrees [data-objective-worktree]'),'shared worktree remains available to another task')})()`);
 await click('[data-objective-bucket=objective] [data-objective-worktree] [data-objective-star]');
 await evaluate(`(async()=>{await until(()=>!document.querySelector('[data-objective-bucket=objective] [data-objective-worktree]'));assert(document.querySelector('.objective-worktrees [data-objective-worktree]')&&!document.querySelector('.objective-task-worktrees [data-objective-worktree]'),'unstarred worktree remains available in Worktrees and assigned to its own task')})()`);
 await click('.objective-sidebar-task [data-open-task]');
 await evaluate(`checkLink('.objective-task-worktrees [data-objective-worktree] [data-select-worktree]',{folder:{root:FIX.checkout,path:'.'}})`);
 await evaluate(`assert(scopeRoot===FIX.checkout,'task worktree retains terminal association and source path');assert(!document.querySelector('[data-project-directory] .objective-star,[data-native-asset-tools]'),'native file stars stay absent after navigation')`);
 await click('.objective-sidebar-task [data-open-task]');
 await evaluate(`(async()=>{const before=await read(),o=before.objectives[0],r=o.resources.find(r=>r.path==='existing file.py'),transfer=new DataTransfer();ensureAsset('[data-objective-resource="'+r.id+'"]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,cancelable:true,dataTransfer:transfer}));document.querySelector('.objective-sidebar-task [data-open-task="'+taskId+'"]').click();document.querySelector('.objective-task-worktrees [data-objective-worktree]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await until(async()=>(await read()).objectives[0].resources.find(a=>a.id===r.id).worktree===o.worktrees[0].id);const updated=(await read()).objectives[0].resources.find(a=>a.id===r.id);assert(updated.path===r.path&&updated.file_root===r.file_root,'worktree scope drop preserves original file ownership and path');LabObjectives.selectObjective(FIX.oid);await until(()=>document.querySelector('[data-objective-bucket=unassigned] [data-objective-resource="'+r.id+'"]'));window.scopedFileId=r.id})()`);
 await click('.objective-worktrees [data-select-worktree="workspace-root"]');
 await evaluate(`assert(!document.querySelector('[data-objective-bucket=unassigned] [data-objective-resource="'+scopedFileId+'"]'),'worktree-scoped resource hides from another scope')`);
 await click('.objective-sidebar-task [data-open-task]');
 await click('.objective-task-worktrees [data-objective-worktree] [data-select-worktree]');
 await evaluate(`assert(!document.querySelector('[data-objective-bucket=unassigned]'),'folder navigation hides unassigned assets');LabObjectives.selectObjective(FIX.oid);assert(document.querySelector('[data-objective-bucket=unassigned] [data-objective-resource="'+scopedFileId+'"]'),'Objective exposes assets for the selected scope')`);
 await evaluate(`(async()=>{
   let d=await read(),response=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'resource',objective_id:FIX.oid,kind:'link',title:'Archived context',url:'https://example.com/archived-context'}})});assert(response.ok,'archive fixture resource');d=await response.json();const r=d.objectives[0].resources.at(-1);
   response=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id:'demo',expected:d.revision,action:{type:'asset-bucket',objective_id:FIX.oid,bucket:'archive',resource_id:r.id}})});assert(response.ok,'archive fixture classification');await LabObjectives.load(undefined,true);
   window.objectivePastesBefore=pasted.length;window.objectiveDataBefore=JSON.stringify(await read());document.getElementById('termBody').style.cssText='position:fixed;right:0;bottom:0;width:260px;height:100px;z-index:200;background:#222';
 })()`);
 const objectivePoints=await evaluate(`(()=>{const source=document.querySelector('.objective-sidebar-heading [data-drag-objective]'),target=document.getElementById('termBody');source.scrollIntoView({block:'nearest'});const a=source.getBoundingClientRect(),b=target.getBoundingClientRect(),p={x:a.x+a.width/2,y:a.y+a.height/2};assert(document.elementFromPoint(p.x,p.y)?.closest('[data-drag-objective]')===source,'whole Objective drag source is visible');return{source:p,target:{x:b.x+b.width/2,y:b.y+b.height/2}}})()`);
 dragData=null;await send('Input.setInterceptDrags',{enabled:true});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...objectivePoints.source});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',...objectivePoints.source,button:'left',buttons:1,clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:objectivePoints.source.x+30,y:objectivePoints.source.y,button:'left',buttons:1});
 for(let i=0;i<100&&!dragData;i++)await new Promise(r=>setTimeout(r,20));
 if(!dragData?.items.some(item=>item.mimeType==='application/x-lab-task-context'))throw Error('Native whole Objective context payload');
 for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...objectivePoints.target,data:dragData});
 await send('Input.setInterceptDrags',{enabled:false});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...objectivePoints.target,button:'left',clickCount:1});
 const whole=JSON.parse(dragData.items.find(item=>item.mimeType==='application/x-lab-task-context').data);
 const wholeRefs=JSON.parse(dragData.items.find(item=>item.mimeType==='application/x-lab-reference').data);
 await evaluate(`(async()=>{const model=${JSON.stringify(whole)},refs=${JSON.stringify(wholeRefs)},o=(await read()).objectives[0],prompt=LabTaskContext.format(model);
   assert(prompt.includes('Global assets (shared across tasks):')&&prompt.includes('Unassigned assets:')&&prompt.includes('Asset index by type:')&&prompt.includes('Task assets and specification:'),'full Objective index separates global, task and unassigned assets by type');
   assert(model.kind==='objective'&&model.objective.title===o.name&&model.tasks.length===o.tasks.reduce((n,t)=>n+1+t.children.length,0),'whole Objective includes every task and subtask');
   assert(pasted.length===objectivePastesBefore+1&&pasted.at(-1)===prompt&&prompt.includes('This objective: ')&&!prompt.includes('Work only on This task:'),'native console drop pastes whole Objective prompt');
   assert(refs.includes(o.manifest_path)&&refs.includes(o.path)&&refs.includes(FIX.checkout)&&refs.includes(FIX.folder+'/query.sql'),'manifest, Objective folder, worktree and attached file references');
   for(const task of o.tasks.flatMap(t=>[t,...t.children])){const r=o.resources.find(r=>r.id===task.document_id);assert(refs.includes(FIX.folder+'/'+r.path+'#tab='+task.tab_id),'every task retains its specification tab');}
   for(const r of o.resources.filter(r=>!o.archived_assets.some(a=>a.resource_id===r.id))){assert(refs.includes(r.kind==='link'?r.url:(r.file_root||FIX.folder)+'/'+r.path)||r.task_document,'unassigned and worktree-scoped resources remain in whole Objective context');}
   assert(!refs.includes('https://example.com/archived-context')&&new Set(refs).size===refs.length,'archived resources excluded and references deduplicated');
   assert(refs.every(ref=>prompt.split('\\n').filter(line=>line.endsWith(' — '+ref)).length===1),'each exact reference appears once in whole Objective prompt');
   assert(JSON.stringify(await read())===objectiveDataBefore,'passing context changes no Objective data or terminal associations');assert(!contentErrors.length,'whole Objective drop has no browser errors');
 })()`);
 const folderTargets=await evaluate(`(async()=>[['workspace-root',FIX.folder],['objective-root',(await read()).objectives[0].path]])()`);
 for(const [id,root] of folderTargets){
   await click('.objective-sidebar-task [data-open-task]');
   await evaluate(`assert(!!document.querySelector('[data-task-mode-head]'),'folder navigation starts from a selected task')`);
   await click('.objective-worktrees [data-select-worktree="'+id+'"]');
   await evaluate(`until(()=>scopeRoot===${JSON.stringify(root)}&&!document.querySelector('[data-task-mode-head]')&&!document.querySelector('[data-task-mode-head]')&&document.querySelector('#content .objective-task-list'));assert(!document.querySelector('.objective-overview')&&document.querySelector('[data-objectives-sidebar]').dataset.worktreeBrowse==='true','folder selection opens unfolded tasks for assignment')`);
 }
 await click('.objective-sidebar-task [data-open-task]');await click('.objective-sidebar-heading [data-select-objective]');
 await evaluate(`(async()=>{const mode=document.querySelector('[data-objective-overview-mode]');mode.value='assets';mode.dispatchEvent(new Event('change',{bubbles:true}));const o=(await read()).objectives[0],host=document.querySelector('.objective-overview');assert(host&&host.querySelector('h2').textContent===o.name&&!document.querySelector('[data-task-mode-head]'),'Objective click exits task mode and opens its overview');assert(document.querySelector('[data-objectives-sidebar]').firstElementChild.classList.contains('objective-sidebar-heading'),'Objective is the top-level sidebar item');assert(host.querySelectorAll('.objective-task-row').length===o.tasks.reduce((count,t)=>count+1+t.children.length,0),'overview shows every task and subtask');for(const r of o.resources.filter(r=>!o.archived_assets.some(a=>a.resource_id===r.id)))assert(host.querySelector('[data-objective-resource="'+r.id+'"]'),'overview includes assets across all worktree scopes');assert(host.textContent.includes('Global assets · shared across tasks')&&host.textContent.includes('Unassigned assets'),'overview categorizes Objective assets');assert(!host.textContent.includes('Archived context'),'overview excludes archived sources')})()`);
 await evaluate(`(async()=>{const o=(await read()).objectives[0];window.linkedParent=o.tasks[0].id;window.linkedChild=o.tasks[0].children[0].id;await LabObjectives.change({type:'terminal',objective_id:FIX.oid,session_id:FIX.session.session_id,task_id:linkedParent});activated.length=0})()`);
 const linkedParentSelector=await evaluate(`'.objective-sidebar-task [data-open-task="'+linkedParent+'"]'`);await click(linkedParentSelector);
 await evaluate(`assert(activated.length===1&&activated[0].length===1&&activated[0][0]===FIX.session.session_id,'task click activates its linked terminal');assert(!editor()&&document.querySelector('.objective-document-preview')&&document.querySelector('[data-task-mode-head]'),'linked terminal activation keeps read-only task details')`);
 await evaluate(`LabObjectives.change({type:'terminal',objective_id:FIX.oid,session_id:FIX.session.session_id,task_id:linkedChild})`);
 await evaluate(`window.activationCount=activated.length`);await click(linkedParentSelector);await evaluate(`assert(activated.length===activationCount,'reassigned terminal no longer activates for the former task')`);
 const linkedChildSelector=await evaluate(`'.objective-sidebar-task [data-open-task="'+linkedChild+'"]'`);await click(linkedChildSelector);
 await evaluate(`(async()=>{assert(activated.at(-1)[0]===FIX.session.session_id,'subtask click activates the reassigned terminal');const links=(await read()).terminal_links;assert(Object.keys(links).length===1&&links[FIX.session.session_id].task_id===linkedChild,'one task or subtask per terminal');const count=activated.length;LabObjectives.openForTerminal(FIX.session);assert(activated.length===count,'terminal navigation does not recursively activate itself');assert(!contentErrors.length,'task activation has no browser errors');LabObjectives.selectObjective(FIX.oid)})()`);
 await evaluate(`(async()=>{const count=pasted.length,transfer=new DataTransfer();transfer.setData('application/x-lab-terminal',FIX.session.name);document.querySelector('.objective-sidebar-heading [data-select-objective]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await until(async()=>(await read()).terminal_links[FIX.session.session_id].main==='objective');await LabObjectives.load(undefined,true);assert(LabObjectives.openForTerminal(FIX.session)&&document.querySelector('.objective-overview'),'reverse Objective drop promotes an ordinary task terminal to the Objective main');await checkLink('.objective-sidebar-heading [data-select-objective]',{objective_id:FIX.oid,resource_id:null,file:null,main:'objective'});const before=await read();assert(!before.terminal_links[FIX.session.session_id].task_id,'main has no task assignment');document.querySelector('.objective-sidebar-task').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));await new Promise(r=>setTimeout(r,75));assert((await read()).revision===before.revision,'fixed main rejects task reassignment');assert(document.querySelector('.objective-overview')&&pasted.length===count,'main association retains its overview without input')})()`);
 await evaluate(`activated.length=0`);await click('.objective-sidebar-heading [data-select-objective]');
 await evaluate(`assert(activated.length===1&&activated[0].length===1&&activated[0][0]===FIX.session.session_id,'Objective click activates the terminal assigned to the whole Objective');assert(document.querySelector('.objective-overview')&&!document.querySelector('[data-task-mode-head]'),'whole Objective activation keeps the overview');const count=activated.length;LabObjectives.openCurrent();assert(activated.length===count,'restoring the current Objective does not override terminal restoration')`);
 await evaluate(`(async()=>{const d=await read();window.otherWorkflow=d.objectives.find(o=>o.id!==FIX.oid).id;LabObjectives.selectObjective(otherWorkflow);assert(!activated.at(-1).length,'another Objective cannot activate this workflow terminal');const count=activated.length;assert(LabObjectives.openForTerminal(FIX.session),'whole Objective terminal navigates back to its workflow');assert(document.querySelector('.objective-overview h2').textContent===d.objectives.find(o=>o.id===FIX.oid).name&&document.querySelector('[data-current-objective]').dataset.selectObjective===FIX.oid,'terminal selects the correct Objective in the center and top bar');assert(activated.length===count,'terminal activation never triggers a second terminal switch')})()`);
 const screenshot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(process.argv[1]+'/objective-overview.png',Buffer.from(screenshot.data,'base64'));
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
        task = objectives.load(monorepo,'demo')['objectives'][0]['tasks'][0]
        assert term._get_workspace_sessions(monorepo,'demo') == [{**saved_session,'label':task['title']}]
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
