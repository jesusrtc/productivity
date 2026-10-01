"""Checkout documents use native checkout terminals without borrowing or relinking."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


@pytest.mark.parametrize('viewport', [1440, 390])
def test_checkout_document_terminal_browser(client, owned_tasks, tmp_path, viewport):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    root, note, context, *_ = owned_tasks
    path = note.relative_to(root).as_posix()
    detail = client.get('/api/assistant/note', params={'path':path}).json()
    details = {}
    def visit(row):
        details[row['path']] = client.get('/api/assistant/note', params={'path':row['path']}).json()
        for child in row['children']:
            visit(child)
    visit(detail['tree'])
    tab = next(row for row in detail['tree']['children'] if row['title'] == 'Context')
    fixture = {'index':client.get('/api/assistant').json(), 'details':details, 'path':path,
               'tab':tab, 'link':{'assistant_root':str(root), 'document_id':note.stem,
                                 'path':path, 'title':'Task document', 'task_id':None}}
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<400;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
const calls=[],shown=[],attachments=[],notices=[],fileOpens=[];
const scope={workspace_id:'demo',vault:'client'};let activeRoot='/trees/topic',releaseLinks,releaseTerminals,holdTerminals=false;
let termCurrentSession='original-document',termCurrentWorkspaceId='demo';
const original={name:'original-document',logical_name:'@document:original-document',workspace_id:'__assistant__',vault:'__assistant__',
 document_source:{workspace_id:'__assistant__',vault:'__assistant__',logical_name:'original'},linked_scope:{root:'/trees/topic'},linked_task:FIX.link,
 label:'Original document conversation',agent:'claude',agent_session_id:'kept-conversation',state:'running'};
let termSessions=[{name:'topic-terminal',logical_name:'topic',workspace_id:'demo',vault:'client',linked_scope:{root:'/trees/topic'},
 label:'Topic agent',agent:'codex',agent_session_id:'topic-conversation',state:'running'},
 {name:'other-terminal',logical_name:'other',workspace_id:'demo',vault:'client',linked_scope:{root:'/trees/other'},label:'Other agent',state:'running'},
 {...original},{name:'plain-terminal',logical_name:'plain',workspace_id:'demo',vault:'client',state:'running'}];
const originalSnapshot=JSON.stringify(original),sessionSnapshot=JSON.stringify(termSessions);
const whole={...FIX.link,id:'whole',kind:'internal',type:'internal-docs',type_name:'Internal docs',tab_id:null};
const tabLink={...whole,id:'tab',tab_id:FIX.tab.id,path:FIX.tab.path,title:'Context'};
const external={id:'ticket',kind:'external',type:'jira',type_name:'Jira',url:'https://tickets.example.invalid/1'};
const types=[{id:'internal-docs',name:'Internal docs',kind:'internal'},{id:'jira',name:'Jira',kind:'external'}];
const metadata={'/trees/topic':{links:[whole,tabLink,external],types,revision:'topic-v1'},
 '/trees/other':{links:[external],types,revision:'other-v1'}};
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.test'),body=options.body?JSON.parse(options.body):null;
 calls.push({path:u.pathname,method:options.method||'GET',body,query:Object.fromEntries(u.searchParams)});
 let data;
 if(u.pathname==='/api/scope-links'){
  const path=body?.path||u.searchParams.get('path');
  if(path.startsWith('/trees/slow'))await new Promise(resolve=>releaseLinks=()=>resolve());
  if(body){assert(body.expected===metadata[path].revision,'scope drop compares fresh metadata revision');metadata[path]={links:body.links.map(row=>({...row,kind:row.kind||'internal',type_name:row.type_name||'Internal docs',path:row.path||FIX.path,title:row.title||'Task document'})),types,revision:metadata[path].revision+'-next'};}
  data=metadata[path]||{links:[whole],types,revision:'slow-v1'};
 }else if(u.pathname==='/api/term/sessions'){
  if(holdTerminals){holdTerminals=false;await new Promise(resolve=>releaseTerminals=()=>resolve());}
  assert(!options.method,'checkout documents must never start a terminal');
  assert(u.searchParams.get('workspace_id')==='demo'&&u.searchParams.get('vault')==='client','terminal reads retain the current workspace and vault');data=termSessions;
 }else if(u.pathname==='/api/assistant')data=FIX.index;
 else if(u.pathname==='/api/assistant/note')data=FIX.details[u.searchParams.get('path')];
 else if(u.pathname==='/api/workspace-documents'&&!options.method)data=[];
 else if(u.pathname==='/api/workspace-documents/attention')data={};
 else throw Error('Unexpected mutation or document-terminal lookup: '+url+' '+(options.method||'GET'));
 return {ok:!!data,json:async()=>structuredClone(data||{detail:'Missing fixture'})};
};
window.Terminal=class{constructor(){throw Error('Must use the existing workspace renderer')}};
window.WebSocket=class{constructor(){throw Error('Must retain the existing workspace connection')}};
window.LabTaskTerminalBridge={context:()=>({...scope,session_name:termCurrentSession}),display:row=>row.label||row.name,
 patch:()=>{throw Error('Must not transfer the original document terminal link')},
 show:async(row,options={})=>{assert(!row.document_source,'never show a borrowed document terminal');assert(options.openDocument===false,'showing a checkout terminal cannot reopen another document');shown.push(row.name);await _termActivateTab(row.name,options);return true}};
const explorerToast=(message,error)=>notices.push({message,error});
const _termActiveWorkspaceId=()=>scope.workspace_id,_termVaultId=()=>scope.vault,_termIsScopeActive=id=>id===scope.workspace_id;
const termDeadSessions=new Set();let _termLinkedNavigationSeq=0;
const _termCancelPendingLinkedFileOpen=()=>{_termLinkedNavigationSeq++};
const _termSyncLinkedScope=async linked=>{if(linked?.root)activeRoot=linked.root};
const _termOpenLinkedFile=async row=>{_termCancelPendingLinkedFileOpen();fileOpens.push(row.name)};
const termAttach=async(name,id)=>{termCurrentSession=name;termCurrentWorkspaceId=id;attachments.push(name)};
'''
    app = (STATIC/'js/lab-app.js').read_text()
    setup += app[app.index('  let _termTabActivationSeq ='):app.index('  function _termHomeAssociationHtml(session)')]
    checks = r'''
(async()=>{
 const panel=()=>document.getElementById('assistantDocumentTerminal');
 const status=()=>panel()?.querySelector('[data-terminal-status]')?.textContent||'';
 const topic=document.querySelector('[data-scope-links="/trees/topic"]');
 await LabScopeLinks.mount(topic,()=>activeRoot==='/trees/topic');
 LabWorkspaceDocuments.configure({workspace:()=>scope,context:()=>scope,fileScope:()=>({...scope,root:activeRoot}),refresh:async()=>{}});
 await LabWorkspaceDocuments.mount(scope,document.getElementById('sidebar'));
 const terminalInput=document.getElementById('terminalInput');terminalInput.value='Unsent terminal draft';
 topic.querySelector('[data-scope-link="0"]').click();await until(()=>status().includes('Uses this folder/worktree'));
 assert(termCurrentSession==='topic-terminal'&&shown.at(-1)==='topic-terminal','folder document selects its native checkout terminal');
 assert(panel().querySelector('[data-terminal-agent]').textContent==='Topic agent','original document terminal is not chosen');
 assert(panel().querySelector('[data-terminal-choose]').hidden&&panel().querySelector('[data-terminal-unlink]').hidden,'scoped document never offers ownership transfer');
 assert(document.getElementById('terminalInput')===terminalInput&&terminalInput.value==='Unsent terminal draft','workspace terminal input and renderer stay intact');
 assert(document.querySelector('#assistantExpandedHost #assistantDocumentModal.active'),'regular folder document uses expanded workspace layout');
 document.querySelector('[data-rail-tab="'+FIX.tab.path+'"]').click();await until(()=>document.querySelector('[data-rail-tab="'+FIX.tab.path+'"][aria-current="page"]'));
 assert(panel().querySelector('[data-terminal-agent]').textContent==='Topic agent','changing document tabs retains the checkout controller');
 const task=FIX.details[FIX.path].document_tasks.tasks[0];
 panel().querySelector('[data-terminal-target]').value=task.id;panel().querySelector('[data-terminal-target]').dispatchEvent(new Event('change'));
 await until(()=>status().includes('Uses this folder/worktree')&&!panel().querySelector('[data-terminal-show]').hidden&&!panel().querySelector('[data-terminal-show]').disabled);
 panel().querySelector('[data-terminal-show]').click();await until(()=>shown.length===2);
 assert(shown.at(-1)==='topic-terminal','task show uses the same checkout terminal');
 await LabDocumentTerminal.link({documentId:FIX.link.document_id,taskId:task.id,database:FIX.link.assistant_root},original,{workspaceId:'__assistant__',vaultId:'__assistant__'});
 assert(notices.at(-1).error&&notices.at(-1).message.includes('attached'),'a foreign terminal cannot take over this checkout document');
 const secondTopic={name:'second-topic-terminal',logical_name:'second-topic',workspace_id:'demo',vault:'client',linked_scope:{root:'/trees/topic'},label:'Second topic agent',state:'running'};termSessions.push(secondTopic);
 await LabDocumentTerminal.link({documentId:FIX.link.document_id,taskId:task.id,database:FIX.link.assistant_root},secondTopic,{workspaceId:'demo',vaultId:'client'});
 assert(termCurrentSession===secondTopic.name&&panel().querySelector('[data-terminal-agent]').textContent===secondTopic.label,'dropping another native checkout terminal selects it without changing ownership');
 AssistantView.closeDocument();topic.querySelector('[data-scope-link="1"]').click();
 await until(()=>document.querySelector('[data-rail-tab="'+FIX.tab.path+'"][aria-current="page"]')&&status().includes('Uses this folder/worktree'));
 AssistantView.closeDocument();
 const article=document.getElementById('document-drag');Object.assign(article.dataset,{terminalDocument:FIX.link.document_id,assistantRoot:FIX.link.assistant_root,documentPath:FIX.path});
 const drop=target=>{const dataTransfer=new DataTransfer();article.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer}));target.dispatchEvent(new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer}));target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer}));article.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer}));};
 drop(document.querySelector('[data-folder-path="/trees/other"]'));await until(()=>metadata['/trees/other'].links.length===2);
 assert(metadata['/trees/other'].links[0].id==='ticket'&&metadata['/trees/other'].links[1].document_id===FIX.link.document_id,'scope row drop adds a reference and preserves other links');
 metadata['/trees/topic']={links:[external],types,revision:'reset-v1'};
 drop(document.querySelector('[data-workspace-documents]'));await until(()=>metadata['/trees/topic'].links.length===2);
 assert(!calls.some(row=>row.path==='/api/workspace-documents'&&row.method==='POST'),'Documents drop in a checkout never imports workspace document terminals');
 await _termActivateTab('other-terminal');await until(()=>status().includes('Uses this folder/worktree'));
 assert(activeRoot==='/trees/other'&&panel().querySelector('[data-terminal-agent]').textContent==='Other agent','terminal activation opens its folder document with its own controller');
 assert(!fileOpens.length,'scope document takes precedence over unrelated file synchronization');
 AssistantView.closeDocument();
 termSessions.push({name:'slow-terminal',logical_name:'slow',workspace_id:'demo',vault:'client',state:'running',linked_scope:{root:'/trees/slow'}});
 await _termActivateTab('slow-terminal');await until(()=>releaseLinks);await _termActivateTab('plain-terminal');releaseLinks();await new Promise(resolve=>setTimeout(resolve,30));
 assert(!document.querySelector('#assistantDocumentModal.active')&&termCurrentSession==='plain-terminal','late scope read cannot reopen a document after a newer terminal click');
 releaseLinks=null;const filesBeforeClose=fileOpens.length;termSessions.push({name:'slow-close-terminal',logical_name:'slow-close',workspace_id:'demo',vault:'client',state:'running',linked_scope:{root:'/trees/slow-close'}});
 await _termActivateTab('slow-close-terminal');await until(()=>releaseLinks);AssistantView.closeDocument();releaseLinks();await new Promise(resolve=>setTimeout(resolve,30));
 assert(!document.querySelector('#assistantDocumentModal.active')&&fileOpens.length===filesBeforeClose,'closing cancels late scope metadata without falling back to another document or file');
 await _termActivateTab('plain-terminal');activeRoot='/trees/topic';holdTerminals=true;const pendingDocument=LabScopeLinks.openDocument(whole,activeRoot);
 await until(()=>releaseTerminals);AssistantView.closeDocument();const shownBefore=shown.length;releaseTerminals();await pendingDocument;
 assert(!document.querySelector('#assistantDocumentModal.active')&&shown.length===shownBefore,'closing while terminals load cancels both document opening and terminal selection');
 activeRoot='/trees/topic';termSessions=termSessions.filter(row=>row.linked_scope?.root!=='/trees/topic'||row.document_source);
 await LabScopeLinks.mount(topic,()=>activeRoot==='/trees/topic');topic.querySelector('[data-scope-link="1"]').click();
 await until(()=>status().startsWith('Attach a terminal'));
 assert(termCurrentSession==='plain-terminal'&&panel().querySelector('[data-terminal-show]').hidden,'missing checkout terminal never falls back to the document terminal');
 assert(JSON.stringify(original)===originalSnapshot&&JSON.stringify(termSessions.find(row=>row.name===original.name))===JSON.stringify(JSON.parse(sessionSnapshot).find(row=>row.name===original.name)),'original terminal ownership, document link and conversation remain unchanged');
 assert(!calls.some(row=>row.path==='/api/term/task-terminals'||row.path==='/api/assistant/document-terminal'||row.path==='/api/term/sessions/metadata'),'checkout flow never looks up or reassigns document-owned terminals');
 AssistantView.closeDocument();document.getElementById('result').textContent='PASS checkout control, exact tabs, document drops, cancellation and preserved original terminals';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','js/views/assistant.js','js/views/assistant-tasks.js',
        'js/lib/document-terminal.js','js/lib/scope-links.js','js/lib/workspace-documents.js'])
    page = tmp_path/'checkout-documents.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/assistant-tasks.css').read_text()+(STATIC/'css/workspace-documents.css').read_text()+'</style><body class="workspace-active"><div id="repoTabs"></div><main id="content">Workspace content</main><aside id="sidebar"><div class="sidebar-scope-chip" data-base-root="/workspace" data-folder-path="/trees/other">Other checkout</div><section class="sidebar-scope-links" data-scope-links="/trees/topic"></section><section data-workspace-documents></section></aside><article id="document-drag" draggable="true" data-assistant-document-drag>Task document</article><input id="terminalInput"><pre id="result">PENDING</pre><script>const FIX='+json.dumps(fixture).replace('</',r'<\/')+';</script><script>'+setup+'</script>'+scripts+'<script>'+checks+'</script>')
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run(['node',str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'scope-documents.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
