"""Real browser interactions for workspace references and modal terminals."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_workspace_document_interactions_browser(client, owned_tasks, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    root, note, *_ = owned_tasks
    path = str(note.relative_to(root))
    detail = client.get('/api/assistant/note', params={'path':path}).json()
    details = {}
    def visit(row):
        details[row['path']] = client.get('/api/assistant/note', params={'path':row['path']}).json()
        for child in row['children']:
            visit(child)
    visit(detail['tree'])
    fixture = {'index':client.get('/api/assistant').json(), 'details':details, 'path':path,
               'link':{'assistant_root':str(root),'document_id':note.stem,'task_id':None,
                       'title':'Task document','path':path}}
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw new Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw new Error('Timed out: '+fn)};
const calls=[], notices=[], documents=[]; let taskLinks=[], activeView=null, pendingIndex=null, pendingDetail=null;
const scope={workspace_id:'demo',vault:'client'};
localStorage.setItem('lab.assistant.tabs-width.v1','210');
let termSessions=[], termCurrentSession=null, termCurrentWorkspaceId=null;
const termDeadSessions=new Set(), fileOpens=[];
const _termActiveWorkspaceId=()=>scope.workspace_id, _termVaultId=()=>scope.vault;
const _termIsScopeActive=id=>id===scope.workspace_id;
const _termCancelPendingLinkedFileOpen=()=>{};
const _termOpenLinkedFile=async session=>fileOpens.push(session.name);
const termAttach=async(name,workspace)=>{termCurrentSession=name;termCurrentWorkspaceId=workspace;};
const _SIDEBAR_VIS_KEY_PREFIX='test-sidebar-', _sidebarViewSuffix=()=>scope.workspace_id;
const source={name:'same-running-process',logical_name:'claude',workspace_id:'demo',vault:'client',label:'Claude conversation',kind:'claude',agent:'claude',agent_session_id:'conversation',created_at:123,
  agent_activity:{state:'completed',completed_at:500,completion_id:'turn'}};
function explorerToast(message,error){notices.push([message,error])}
const background={...source,name:'background-process',agent_session_id:'background-conversation'};
function termRenderSessionList(){
 if(window.LabDocumentTerminal?.watchCompletion?.())return;
 if(activeView)LabTerminalCompletion.watch('client::demo',background);
}
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://example.test'), body=options.body?JSON.parse(options.body):null;
 calls.push([u.pathname,options.method||'GET',body]);
 let result={};
 if(u.pathname==='/api/assistant'){if(pendingIndex)await pendingIndex;result=FIX.index;}
 else if(u.pathname==='/api/assistant/note'){if(pendingDetail)await pendingDetail;result=FIX.details[u.searchParams.get('path')];}
 else if(u.pathname==='/api/term/task-terminals')result=taskLinks;
 else if(u.pathname==='/api/assistant/document-terminal'){assert(body.action==='status','opening must not create a process');result={state:'absent'}}
 else if(u.pathname==='/api/workspace-documents/attention')result={'client::demo':[source],'client::inactive':[source]};
 else if(u.pathname==='/api/workspace-documents/unlink-terminal'){taskLinks=[];result={ok:true}}
 else if(u.pathname==='/api/workspace-documents'){
  if(options.method==='POST')documents.splice(0,documents.length,FIX.link);
  if(options.method==='DELETE')documents.splice(0);
  result=options.method?{ok:true}:(u.searchParams.get('workspace_id')==='__assistant__'?taskLinks.map(row=>row.linked_task):documents);
 } else throw new Error('Unexpected request '+url);
 return {ok:!!result,json:async()=>structuredClone(result||{})};
};
let sockets=0;
class FakeSocket {static OPEN=1;readyState=1;constructor(url){sockets++;assert(url.includes(source.name),'must attach the same process')}send(){}close(){this.readyState=3}}
window.WebSocket=FakeSocket;
window.Terminal=class {cols=80;rows=24;loadAddon(){}open(host){host.textContent='Existing Claude conversation — same running session';}onData(){return {dispose(){}}}dispose(){}write(){}focus(){}};
window.FitAddon={FitAddon:class{fit(){}}};
window.ensureTerminalLibs=async()=>{};
window.LabTaskTerminalBridge={patch:async(session,patch,context)=>{
 assert(session.name===source.name,'same source session');
 calls.push(['patch','PATCH',{patch,context}]);
 taskLinks=patch.linked_task?[{...source,state:'running',linked_task:FIX.link}]:[];
}};
'''
    app = (STATIC / 'js/lab-app.js').read_text()
    setup += app[app.index('  let _termTabActivationSeq ='):app.index('  function _termHomeAssociationHtml(session)')]
    setup += app[app.index('  function sidebarToggleCollapse()'):app.index('  function _sidebarApplyForView()')]
    checks = r'''
(async()=>{
 const W=LabWorkspaceDocuments;
 W.configure({workspace:()=>scope,refresh:async()=>{}});
 await W.mount(scope,document.getElementById('sidebar'));
 // Drag the actual document button area, rather than relying on blank row padding.
 const article=document.getElementById('document-drag');
 article.dataset.terminalDocument=FIX.link.document_id;article.dataset.assistantRoot=FIX.link.assistant_root;
 const transfer=new DataTransfer();
 article.querySelector('strong').dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:transfer}));
 assert(JSON.parse(transfer.getData('application/x-lab-assistant-document')).document_id===FIX.link.document_id,'stable document drag identity');
 const target=document.querySelector('[data-workspace-id="demo"]');
 target.dispatchEvent(new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 assert(target.classList.contains('workspace-document-drop'),'drop target highlighted');
 target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:transfer}));
 await until(()=>document.querySelector('.workspace-document-open'));
 const docRow=document.querySelector('.workspace-document');
 assert(docRow.compareDocumentPosition(document.getElementById('recent'))&Node.DOCUMENT_POSITION_FOLLOWING,'Documents above Recently updated');
 assert(LabDocumentTerminal.dropContext(docRow).documentId===FIX.link.document_id,'terminal drop resolves the linked document');
 await LabDocumentTerminal.link(LabDocumentTerminal.dropContext(docRow),source,{workspaceId:'demo',vaultId:'client'});
 W.selectTerminal(taskLinks[0],scope);
 assert(docRow.classList.contains('terminal-selected'),'selecting a terminal highlights its document');
 assert(!document.querySelector('#assistantDocumentModal.active'),'passive terminal refresh only highlights the document');
 await W.mount(scope,document.getElementById('sidebar'),true);
 assert(document.querySelector('.workspace-document.terminal-selected'),'selection survives refresh');
 W.selectTerminal(source,{workspace_id:'other',vault:'client'});
 assert(!docRow.classList.contains('terminal-selected'),'selection never leaks between workspaces');
 W.selectTerminal(taskLinks[0],scope);
 termSessions=[{...taskLinks[0],linked_file:{root:'/repo',path:'other.md'}}, {...source,name:'unlinked'}];
 await _termActivateTab(source.name);
 assert(termCurrentSession===source.name&&termCurrentWorkspaceId==='demo','terminal attaches immediately in its original workspace');
 await until(()=>document.querySelector('#assistantInlineHost #assistantDocumentModal.active'));
 assert(!sockets&&!fileOpens.length,'linked document takes precedence over file sync without creating a renderer');
 assert(!document.body.classList.contains('sidebar-collapsed')&&getComputedStyle(document.getElementById('sidebar')).display!=='none','terminal click keeps Files visible');
 AssistantView.closeInlineDocument();
 // A newer unlinked terminal cancels a slow document open at either fetch stage.
 for(const stage of ['index','detail']){
  let finish;const pending=new Promise(resolve=>finish=resolve);
  if(stage==='index')pendingIndex=pending;else pendingDetail=pending;
  const count=calls.filter(row=>row[0]==='/api/assistant/note').length;
  await _termActivateTab(source.name);
  if(stage==='detail')await until(()=>calls.filter(row=>row[0]==='/api/assistant/note').length>count);
  await _termActivateTab('unlinked');finish();
  pendingIndex=null;pendingDetail=null;
  await new Promise(resolve=>setTimeout(resolve,30));
  assert(!document.querySelector('#assistantDocumentModal.active'),'newer terminal wins during '+stage+' fetch');
 }
 W.selectTerminal(taskLinks[0],scope);
 docRow.querySelector('button').click();
 await until(()=>document.querySelector('#assistantInlineHost #assistantDocumentModal.active'));
 assert(!document.body.classList.contains('sidebar-collapsed'),'Files stays visible when opening from the sidebar');
 assert(getComputedStyle(document.getElementById('content')).display==='none','inline document replaces main content');
 assert(document.querySelector('.assistant-document-modal').getAttribute('role')==='region','inline document is not a dialog');
 assert(!sockets&&!LabDocumentTerminal.watchCompletion(),'inline view reuses regular terminal panel');
 const inlineRect=document.querySelector('.assistant-document-modal').getBoundingClientRect();
 assert(inlineRect.height>700&&inlineRect.bottom<=innerHeight+1,'inline document fits available viewport');
 assert(document.querySelector('.workspace-document.document-open'),'opened document marked');
 document.querySelector(`[data-record-path="${FIX.path}"]`).click();
 await until(()=>!document.getElementById('assistantEditNote').hidden);
 document.getElementById('assistantEditNote').click();
 await until(()=>document.querySelector('.assistant-note-editor textarea'));
 const draft=document.querySelector('.assistant-note-editor textarea');
 draft.value='Draft kept while expanding';draft.dispatchEvent(new Event('input',{bubbles:true}));
 document.getElementById('assistantExpandDocument').click();
 assert(document.querySelector('.assistant-note-editor textarea')===draft&&draft.value==='Draft kept while expanding','Expand preserves editor and unsaved draft');
 await until(()=>sockets===1);
 assert(!document.body.classList.contains('sidebar-collapsed'),'Expand keeps Files visible');
 assert(document.body.classList.contains('workspace-active'),'opening preserves workspace');
 const modal=document.querySelector('.assistant-document-modal');
 const select=document.querySelector('select[data-terminal-placement]');
 select.value='right';select.dispatchEvent(new Event('change'));
 assert(getComputedStyle(modal).display==='grid','right layout is a real side-by-side split');
 const body=document.querySelector('.assistant-modal-body').getBoundingClientRect(), terminal=document.getElementById('assistantDocumentTerminal').getBoundingClientRect();
 assert(terminal.left>=body.right-1&&Math.abs(terminal.top-body.top)<2,'terminal placed right of document');
 select.value='bottom';select.dispatchEvent(new Event('change'));
 assert(document.getElementById('assistantDocumentTerminal').getBoundingClientRect().top>=document.querySelector('.assistant-modal-body').getBoundingClientRect().bottom-1,'bottom placement');
 select.value='right';select.dispatchEvent(new Event('change'));
 assert(sockets===1,'changing layout never reconnects or launches');
 // The inactive workspace gets the same unread state without being opened.
 await W.poll(true);
 assert(document.querySelectorAll('.workspace-attention-dot').length===2,'active and inactive workspace dots');
 assert(getComputedStyle(document.querySelector('.workspace-attention-dot')).animationName==='workspace-attention-blink','green dot blinks');
 assert(LabTerminalCompletion.meta('client::demo',background),'background response starts unread');
 LabTerminalCompletion.setDelaySeconds(1);activeView=true;termRenderSessionList();
 await until(()=>!document.querySelector('.workspace-attention-dot'));
 assert(LabTerminalCompletion.meta('client::demo',background),'modal review never acknowledges its obscured background terminal');
 activeView=null;LabTerminalCompletion.stopViewing();
 source.agent_activity={state:'completed',completed_at:600,completion_id:'next'};
 await W.poll(true);assert(document.querySelectorAll('.workspace-attention-dot').length===2,'next response alerts again');
 // Cancel is a no-op; both ownership choices send the captured source and target.
 let pending=W.unlink(taskLinks[0]);await until(()=>document.querySelector('dialog[open]'));
 document.querySelector('dialog button[value="cancel"]').click();assert(await pending===false,'cancel');
 assert(!calls.some(row=>row[0].endsWith('/unlink-terminal')),'cancel writes nothing');
 for(const destination of ['workspace','assistant']){
  pending=W.unlink({...source,linked_task:FIX.link});await until(()=>document.querySelector('dialog[open]'));
  document.querySelector(`dialog button[value="${destination}"]`).click();assert(await pending,'unlink completed');
  const sent=calls.filter(row=>row[0].endsWith('/unlink-terminal')).at(-1)[2];
  assert(sent.destination===destination&&sent.source_workspace_id==='demo'&&sent.name==='claude','explicit destination and original source');
 }
 AssistantView.closeDocument();
 taskLinks=[{...source,state:'running',linked_task:FIX.link}];
 await AssistantView.openLinkedTask(FIX.link);
 await until(()=>document.querySelector('select[data-terminal-placement]')?.value==='right');
 AssistantView.closeDocument();
 // Assistant derives its own Linked documents section from saved terminal links.
 const assistant={workspace_id:'__assistant__',vault:'__assistant__'};
 await W.mount(assistant,document.getElementById('sidebar'),true);
 assert(document.querySelector('[data-workspace-documents] .sidebar-title').textContent.includes('Linked documents'),'Assistant section');
 assert(!document.querySelector('.workspace-document-remove'),'derived links cannot be removed as workspace references');
 W.selectTerminal(taskLinks[0],assistant);
 assert(document.querySelector('.workspace-document.terminal-selected'),'Assistant selection highlight');
 document.body.classList.add('sidebar-collapsed');
 await AssistantView.openLinkedTask(FIX.link,{inline:true});
 assert(document.body.classList.contains('sidebar-collapsed'),'opening preserves a manually collapsed sidebar');
 sidebarToggleCollapse();
 assert(localStorage.getItem('test-sidebar-demo')==='1','Files toggle persists while a document is open');
 AssistantView.closeInlineDocument();
 assert(!document.body.classList.contains('sidebar-collapsed'),'closing preserves the latest Files visibility');
 await AssistantView.openLinkedTask(FIX.link,{inline:true});sidebarToggleCollapse();
 AssistantView.closeInlineDocument();
 assert(document.body.classList.contains('sidebar-collapsed')&&localStorage.getItem('test-sidebar-demo')==='0','closing also preserves an explicit collapse');
 assert(document.getElementById('content').textContent==='Original file content','file content preserved after close');
 document.body.classList.remove('sidebar-collapsed');
 let resolveIndex;pendingIndex=new Promise(resolve=>resolveIndex=resolve);
 const opening=AssistantView.openLinkedTask(FIX.link,{inline:true});
 AssistantView.closeInlineDocument();resolveIndex();await opening;pendingIndex=null;
 assert(!document.querySelector('#assistantDocumentModal.active'),'navigation cancels pending document open');
 // A workspace sidebar double-click opens the dialog directly.
 const doubleClick=button=>{
  button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
  button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:2}));
  button.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2}));
 };
 doubleClick(document.querySelector('.workspace-document-open'));
 await until(()=>document.querySelector('#assistantDocumentModal.active:not(.assistant-document-inline)'));
 assert(document.querySelector('.assistant-document-modal').getAttribute('aria-modal')==='true','double-click opens an accessible dialog');
 AssistantView.closeDocument();
 document.body.classList.replace('workspace-active','assistant-active');
 AssistantView.init({section:'documents'});
 await until(()=>document.querySelector('[data-assistant-document]'));
 const row=()=>[...document.querySelectorAll('[data-assistant-document]')].find(button=>button.dataset.assistantDocument===FIX.path);
 const singleClick=()=>row().dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
 singleClick();
 await until(()=>AssistantView.isInlineDocument()&&!document.querySelector('#assistantDocumentModal[aria-busy]'));
 assert(document.querySelector('.assistant-document-modal').getAttribute('role')==='region','Assistant single click defaults to inline');
 assert(getComputedStyle(document.getElementById('content')).display==='none','Assistant chooser replaced with document');
 assert(document.querySelector('[data-metadata-field="workspace"]').closest('.assistant-metadata-more'),'organization fields live in Properties');
 assert(document.querySelector('[data-edit-attributes]').closest('.assistant-metadata-more'),'attributes remain accessible under Properties');
 const copy=document.querySelector('.assistant-copy-menu');
 copy.querySelector('summary').click();
 assert(copy.open&&document.getElementById('assistantCopyRich').getBoundingClientRect().height>=36,'Copy menu exposes both formats at comfortable size');
 document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert(!copy.open&&AssistantView.isInlineDocument(),'Escape dismisses Copy without closing document');
 AssistantView.closeDocument();
 assert(getComputedStyle(document.getElementById('content')).display!=='none','close returns to Assistant chooser');
 doubleClick(row());
 await until(()=>document.querySelector('#assistantDocumentModal.active:not(.assistant-document-inline)'));
 await new Promise(resolve=>setTimeout(resolve,350));
 assert(!AssistantView.isInlineDocument(),'single-click timer cannot replace double-click dialog');
 AssistantView.closeDocument();
 singleClick();AssistantView.closeInlineDocument();
 await new Promise(resolve=>setTimeout(resolve,350));
 assert(!document.querySelector('#assistantDocumentModal.active'),'navigation cancels delayed pointer opens');
 singleClick();await until(()=>AssistantView.isInlineDocument());
 document.getElementById('assistantInlineHost').style.maxWidth='740px';
 const header=document.querySelector('.assistant-modal-header');
 assert(header.scrollWidth<=header.clientWidth+1,'inline header fits a narrow workspace');
 const title=document.getElementById('assistantModalTitle');
 assert(title.getBoundingClientRect().width>80&&title.scrollWidth<=title.clientWidth+1,'document title stays readable alongside draft actions');
 assert(!notices.some(row=>row[1]),'no errors');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>' + (STATIC / name).read_text() + '</script>' for name in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','js/lib/document-terminal.js','js/lib/terminal-completion.js',
        'js/lib/workspace-documents.js','js/views/assistant.js','js/views/assistant-tasks.js'])
    css = '\n'.join((STATIC / name).read_text() for name in ['css/lab-shell.css','css/assistant-tasks.css','css/workspace-documents.css'])
    page = tmp_path / 'workspace-documents.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>:root{--accent:#58a6ff;--text-primary:#e6edf3;--text-secondary:#8b949e;--bg-secondary:#161b22;--border:#30363d;--green:#3fb950}body{background:#0d1117;color:#e6edf3}'+css+'</style><body class="workspace-active"><div id="workspaceTabs" style="position:fixed;top:0"><div class="workspace-tab" data-kind="workspace" data-workspace-id="demo" data-vault="client">Demo<button class="x">×</button></div><div class="workspace-tab" data-kind="workspace" data-workspace-id="inactive" data-vault="client">Inactive<button class="x">×</button></div></div><div id="sidebar" class="sidebar"><section data-workspace-documents></section><div id="recent">Recently updated</div></div><article style="position:fixed;top:40px" id="document-drag" data-assistant-document-drag draggable="true"><button class="assistant-document-row"><strong>Task document</strong></button></article><div class="layout"><div id="content" class="main">Original file content</div></div><pre id="result">PENDING</pre><script>const FIX='+json.dumps(fixture).replace('</','<\\/')+';'+setup+'</script>'+scripts+'<script>'+checks+'</script>')
    profile = tmp_path / 'profile'
    browser = subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        driver = tmp_path / 'focused-browser.mjs'
        resize_checks = r'''
async function evaluate(expression) {
 const result = await send('Runtime.evaluate', {expression,returnByValue:true,awaitPromise:true});
 if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description || 'Browser evaluation failed');
 return result.result?.value;
}
if(await evaluate("document.getElementById('result').textContent") === 'PASS') {
 await evaluate(`assert(!document.querySelector('.tabs-open')&&document.getElementById('assistantTabsDrawer').inert,'tabs start hidden with no invisible focus targets')`);
 async function revealTabs() {
  const point=await evaluate(`(() => {const r=document.querySelector('.assistant-tabs-edge').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+30}})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
  await evaluate(`assert(document.querySelector('.tabs-open')&&!document.getElementById('assistantTabsDrawer').inert,'left edge hover reveals tabs')`);
 }
 const geometry = () => evaluate(`(() => {
  const nav=document.getElementById('assistantDocumentNav').getBoundingClientRect();
  const handle=document.querySelector('.assistant-tabs-resizer').getBoundingClientRect();
  return {width:nav.width,x:handle.x+handle.width/2,y:handle.y+60};
 })()`);
 async function dragBy(delta) {
  await revealTabs();
  const {x,y}=await geometry();
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:x+delta,y,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:x+delta,y,button:'left',clickCount:1});
 }
 await revealTabs();
 await evaluate(`(() => {
  assert(localStorage.getItem('lab.assistant.tabs-width.v2')==='420','previous narrow width upgrades to the wider drawer');
  const title=[...document.querySelectorAll('.assistant-record-title')].at(-1), previous=title.textContent;
  title.textContent='Decision log and follow-up actions for the September product planning meeting';
  assert(title.getBoundingClientRect().height>24&&title.scrollWidth<=title.clientWidth+1,'long nested tab titles wrap without clipping');
  title.textContent=previous;
 })()`);
 await dragBy(140);
 if((await geometry()).width!==560)throw new Error('Dragging must widen tabs from 420 to 560 pixels');
 await dragBy(-380);
 if((await geometry()).width!==180)throw new Error('Dragging must narrow tabs to 180 pixels');
 await dragBy(2000);
 await evaluate(`(() => {
  const body=document.getElementById('assistantModalBody').getBoundingClientRect();
  const drawer=document.getElementById('assistantTabsDrawer').getBoundingClientRect();
  assert(body.right-drawer.right>=63,'wide drawer leaves content exposed for hover dismissal');
  assert(document.getElementById('assistantDocumentNav').getBoundingClientRect().width===650,'overlay uses the available width in a narrow workspace');
 })()`);
 await dragBy(-2000);
 if((await geometry()).width!==160)throw new Error('Minimum keeps tab controls usable');
 await dragBy(160);
 await evaluate(`(async()=>{
  assert(!document.body.classList.contains('assistant-tabs-resizing'),'pointer release cleans up drag state');
  const draft=document.querySelector('.assistant-note-editor textarea');
  document.getElementById('assistantExpandDocument').click();
  assert(document.getElementById('assistantDocumentNav').getBoundingClientRect().width===320,'Expand preserves width');
  assert(document.querySelector('.assistant-note-editor textarea')===draft,'resizing preserves editor');
  AssistantView.closeDocument();
  document.getElementById('assistantDocumentModal').remove();
  await AssistantView.openDocument('note',FIX.path);
  assert(document.getElementById('assistantDocumentNav').getBoundingClientRect().width===320,'new document view restores stored width');
  const handle=document.querySelector('.assistant-tabs-resizer');
  handle.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));
  assert(document.getElementById('assistantDocumentNav').getBoundingClientRect().width===304,'keyboard narrows tabs');
  handle.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
  assert(document.getElementById('assistantDocumentNav').getBoundingClientRect().width===420,'double-click restores the wider default');
 })()`);
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:false});
 await evaluate(`assert(getComputedStyle(document.querySelector('.assistant-tabs-resizer')).display==='none','mobile keeps horizontal tabs')`);
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
 await dragBy(110);
 const contentPoint=await evaluate(`(() => {const r=document.getElementById('assistantModalDocument').getBoundingClientRect();return {x:r.right-30,y:r.y+80}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...contentPoint});
 await evaluate(`assert(!document.querySelector('.tabs-open'),'moving back into content hides tabs')`);
 const before=await evaluate(`document.getElementById('assistantModalDocument').getBoundingClientRect().width`);
 await revealTabs();
 await evaluate(`assert(document.getElementById('assistantModalDocument').getBoundingClientRect().width===${before},'drawer overlays without shifting the document')`);
 const target=await evaluate(`(() => {const tab=[...document.querySelectorAll('[data-record-path]')].at(-1);const r=tab.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,path:tab.dataset.recordPath}})()`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:target.x,y:target.y});
 await send('Input.dispatchMouseEvent',{type:'mousePressed',x:target.x,y:target.y,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:target.x,y:target.y,button:'left',clickCount:1});
 await evaluate(`until(()=>document.querySelector('[data-record-path="${target.path}"][aria-current="page"]'))`);
 await evaluate(`until(()=>document.getElementById('assistantDocumentLocation').textContent.includes('Research'))`);
 await evaluate(`assert(document.getElementById('assistantDocumentLocation').textContent.includes('Context'),'breadcrumb includes parent tab')`);
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',...contentPoint});
 await evaluate(`assert(!document.querySelector('.tabs-open'),'selection followed by moving out dismisses drawer')`);
 await evaluate(`(() => {
  const host=document.getElementById('assistantModalDocument');
  host.innerHTML='<div class="assistant-markdown"><h2>Opening section</h2><div style="height:1400px"></div><h2>Later section</h2><div style="height:1400px"></div></div>';
  host.scrollTop=1450;
 })()`);
 await evaluate(`until(()=>document.getElementById('assistantDocumentLocation').textContent.includes('Later section'))`);
 await revealTabs();
 await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await evaluate(`assert(!document.querySelector('.tabs-open')&&AssistantView.isInlineDocument(),'Escape dismisses tabs without closing document')`);
}
'''
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace(
            "await send('Page.enable');", "await send('Page.enable');\nawait send('Emulation.setFocusEmulationEnabled', {enabled:true});").replace(
            "const evaluated = await send('Runtime.evaluate', {", resize_checks + "\nconst evaluated = await send('Runtime.evaluate', {"))
        subprocess.run(['node',str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'workspace-documents.png')],check=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        html = (tmp_path/'dom.html').read_text()
        result = re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
        assert result and result[1] == 'PASS', result[1] if result else html[-2000:]
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Real pointer input enables the unsaved-draft beforeunload prompt.
            browser.kill()
            browser.wait(timeout=5)
