"""Real xterm lifecycle in Chrome; fake transport prevents agent/API calls."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from .test_assistant_documents_unified import library

ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'core/src/core/static'


@pytest.mark.parametrize('viewport', [1440, 390])
def test_document_terminal_browser(client, library, tmp_path, viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:pytest.skip('Chrome and Node required')
    root,task,note,tab,*_=library
    from lab import assistant_tasks as tasks, assistant_records as records, assistant_storage as storage
    refs=[str(path.relative_to(root)) for path in (task,note,tab)]
    storage.migrate(root,dry_run=False)
    task,note,tab=[records.resolve(root,ref)[0] for ref in refs]
    tasks.migrate(root,dry_run=False)
    tasks.change(root,note.stem,{'title':'Task A','tab_id':note.stem})
    tasks.change(root,note.stem,{'title':'Task B','tab_id':records.resolve(root,str(tab.relative_to(root)))[1]['id']})
    paths={key:path.relative_to(root).as_posix() for key,path in [('task',task),('note',note),('tab',tab)]}
    details={path:client.get('/api/assistant/note',params={'path':path}).json() for path in paths.values()}
    fixtures={'paths':paths,'details':details,'index':client.get('/api/assistant').json()}
    checks=r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw new Error('Timed out: '+fn)};
const counters={terminals:0,sockets:0,peakTerminals:0,peakSockets:0,created:0,opened:0,resumed:0,patches:0};
const intervals=new Map();let timerId=50000;
const realInterval=window.setInterval,realClearInterval=window.clearInterval;
window.setInterval=(fn,delay)=>{if(delay===30000){intervals.set(++timerId,fn);return timerId;}return realInterval(fn,delay)};
window.clearInterval=id=>{intervals.delete(id);realClearInterval(id)};
const OriginalTerminal=Terminal;
window.Terminal=class extends OriginalTerminal {
 constructor(options){super(options);++counters.terminals;++counters.created;counters.peakTerminals=Math.max(counters.terminals,counters.peakTerminals);window.latestTerminal=this;}
 dispose(){--counters.terminals;super.dispose();}
};
window.ensureTerminalLibs=async()=>{};
let latestSocket;
window.WebSocket=class {
 static OPEN=1;
 constructor(url){this.url=url;this.readyState=1;this.messages=[];latestSocket=this;++counters.sockets;counters.peakSockets=Math.max(counters.sockets,counters.peakSockets);queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:'data',data:'Existing conversation.\r\nPrevious draft stays here.\r\n> '})}));}
 send(data){this.messages.push(JSON.parse(data));}
 close(){if(this.readyState===1){this.readyState=3;--counters.sockets;}}
};
let hidden=false;Object.defineProperty(document,'hidden',{get:()=>hidden});
const sessions=[{name:'existing-one',logical_name:'one',workspace_id:'work',workspace_name:'My workspace',vault:'local',label:'Existing one',agent:'codex',state:'running'},
 {name:'existing-two',logical_name:'two',workspace_id:'elsewhere',workspace_name:'Other workspace',vault:'second-vault',label:'Existing two',agent:'claude',state:'running'}];
const managed=new Map();
window.LabTaskTerminalBridge={patch:async(session,patch,context)=>{
 ++counters.patches;
 const target=sessions.find(row=>row.logical_name===session.logical_name&&row.workspace_id===context.workspaceId&&row.vault===context.vaultId);
 assert(target,'source vault/workspace preserved');
 const link=patch.linked_task;
 for(const row of sessions)if(link&&row.linked_task?.document_id===link.document_id&&row.linked_task?.task_id===link.task_id)row.linked_task=null;
 target.linked_task=link;
 return structuredClone(target);
}};
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/term/sessions'&&options.method==='POST'){const body=JSON.parse(options.body),row=sessions.find(row=>row.logical_name===body.name);assert(row&&row.state==='stopped','resume exact saved session');row.state='running';++counters.resumed;return {ok:true,json:async()=>row};}
 if(u.pathname==='/api/term/task-terminals')return {ok:true,json:async()=>structuredClone(sessions.filter(row=>u.searchParams.has('document_id')?row.linked_task?.document_id===u.searchParams.get('document_id'):row.state==='running'))};
 if(u.pathname==='/api/assistant/document-terminal'){
  const {path,action}=JSON.parse(options.body),detail=FIX.details[path],key=detail.root_path||path;
  if(action==='open'){++counters.opened;managed.set(key,{name:'old-managed',state:'running',agent:'codex'});}
  if(action==='sleep')managed.get(key).state='sleeping';
  return {ok:true,json:async()=>({...managed.get(key)||{state:'absent'}})};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
const host=()=>document.getElementById('assistantDocumentTerminal');
const poll=async()=>{for(const fn of intervals.values())fn();await new Promise(r=>setTimeout(r,20));};
const choose=async()=>{host().querySelector('[data-terminal-choose]').click();await until(()=>host().querySelector('[draggable=true]'));return host().querySelectorAll('[draggable=true]')};
const drag=(source,target)=>{const dataTransfer=new DataTransfer();source.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer}));const hover=new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer});target.dispatchEvent(hover);assert(hover.defaultPrevented&&target.closest('[data-terminal-document]').classList.contains('term-link-drop-target'),'drop preview');target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer}));source.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer}));};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>document.querySelector('[data-assistant-document]'));
 document.querySelector('[data-assistant-view="all"]').click();
 document.querySelector(`[data-assistant-document="${FIX.paths.note}"]`).click();
 await until(()=>host()?.textContent.includes('Drag a terminal'));
 assert(!counters.opened&&!counters.sockets,'opening task allocates no terminal');
 assert(host().getBoundingClientRect().height<180,'unlinked panel stays compact');
 const note=FIX.details[FIX.paths.note],task=note.document_tasks.tasks.find(task=>task.title==='Task A');
 const row=document.querySelector(`[data-task="${task.id}"]`);
 assert(row,'task row exists in dashboard');
 const choices=await choose();drag(choices[0],row.querySelector('.assistant-tasks-task-label'));
 await until(()=>counters.sockets===1);
 assert(latestSocket.url.includes('existing-one')&&latestSocket.url.includes('cols=')&&latestSocket.url.includes('rows='),'existing session and real geometry');
 assert(!counters.opened&&counters.patches===1,'drop never starts a process');
 assert(row.querySelector('.assistant-linked-terminal'),'task shows link');
 const before=counters.created;
 document.querySelector(`[data-record-path="${FIX.paths.tab}"]`).click();
 await until(()=>document.querySelector(`[data-record-path="${FIX.paths.tab}"].active`));
 assert(counters.created===before,'content-tab navigation preserves same connection');
 latestTerminal.paste('my unsent draft');
 await until(()=>latestSocket.messages.some(message=>message.type==='input'&&message.data==='my unsent draft'));
 const initialName=latestSocket.url;
 AssistantView.closeDocument();assert(!counters.sockets&&!counters.terminals&&!intervals.size,'close releases browser resources');
 document.querySelector(`[data-assistant-document="${FIX.paths.note}"]`).click();
 await until(()=>counters.sockets===1);
 assert(latestSocket.url===initialName&&!counters.opened,'reopen remembers task and exact existing session');
 hidden=true;document.dispatchEvent(new Event('visibilitychange'));
 assert(!counters.sockets&&!counters.terminals,'hidden browser releases renderer');
 hidden=false;document.dispatchEvent(new Event('visibilitychange'));await until(()=>counters.sockets===1);
 latestSocket.onmessage({data:JSON.stringify({type:'exit'})});
 await until(()=>host().textContent.includes('Terminal disconnected'));
 await poll();assert(!counters.sockets&&!counters.opened,'EOF never starts replacement');
 host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);
 const replacement=await choose();replacement[1].click();
 await until(()=>latestSocket.url.includes('existing-two')&&counters.sockets===1);
 assert(!sessions[0].linked_task&&sessions[1].linked_task.task_id===task.id,'reassign transfers only link');
 host().querySelector('[data-terminal-unlink]').click();await until(()=>!counters.sockets);
 assert(sessions.every(row=>row.state==='running')&&!counters.opened,'unlink leaves all processes running');
 // Link the document independently, then confirm a stopped session cannot restart itself.
 host().querySelector('[data-terminal-target]').value='';host().querySelector('[data-terminal-target]').dispatchEvent(new Event('change'));
 await poll();const documentChoices=await choose();documentChoices[0].click();await until(()=>counters.sockets===1);
 sessions[0].state='stopped';await poll();assert(!counters.sockets&&host().textContent.includes('Linked terminal is stopped'),'stopped terminal retains link');
 await poll();assert(!counters.opened,'polling never resumes stopped terminals');
 host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);assert(counters.resumed===1,'only an explicit click resumes the saved linked session');
 for(let i=0;i<12;i++){
  LabDocumentTerminal.open(FIX.details[i%2?FIX.paths.note:FIX.paths.task]);
  await until(()=>host().textContent.includes(i%2?'Running':'Drag a terminal'));
 }
 assert(counters.peakSockets===1&&counters.peakTerminals===1,'switching never accumulates display resources');
 LabDocumentTerminal.close();
 // Retained legacy conversations are opt-in; existing saved IDs remain recoverable.
 managed.set(FIX.paths.task,{name:'old-managed',state:'sleeping',agent:'codex'});
 LabDocumentTerminal.open(FIX.details[FIX.paths.task]);await until(()=>host().textContent.includes('Resume previous conversation'));
 assert(!counters.opened,'sleeping history never auto-wakes');
 host().querySelector('[data-terminal-wake]').click();await until(()=>counters.sockets===1);
 assert(counters.opened===1&&latestSocket.url.includes('old-managed'),'explicit resume still works');
 LabDocumentTerminal.close();
 LabDocumentTerminal.open(note);await until(()=>counters.sockets===1);
 assert(counters.peakSockets===1&&counters.peakTerminals===1,'one visible connection');
 document.getElementById('result').textContent='PASS '+JSON.stringify(counters);
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);

'''
    scripts='\n'.join('<script>'+ (STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'vendor/xterm@5.3.0/xterm.min.js','vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js',
        'js/lib/markdown-content.js','js/views/assistant-tasks.js','js/views/assistant.js','js/lib/document-terminal.js'])
    app=(STATIC/'js/lab-app.js').read_text()
    guard=app[app.index('  function _termGuardViewportDisposal('):app.index('  function termEnsureXterm(')]
    page=tmp_path/'document-terminal.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/assistant-tasks.css').read_text()+(STATIC/'vendor/xterm@5.3.0/xterm.min.css').read_text()+
       '</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+'<script>'+guard+'\nconst FIX='+json.dumps(fixtures).replace('</','<\\/')+';\n'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'document-terminal.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
    print(tmp_path/'document-terminal.png',result[1])
