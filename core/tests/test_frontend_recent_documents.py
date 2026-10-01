"""Document opening history in a real browser, including reload and scope changes."""
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


def test_recent_documents_browser(client, owned_tasks, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    root, note, context, _, series, _ = owned_tasks
    details = {}
    for document, kind in [(note, 'note'), (context, 'note'), (series, 'meeting-series')]:
        path = str(document.relative_to(root))
        detail = client.get('/api/assistant/' + kind, params={'path': path}).json()
        details[path] = detail
        def visit(row):
            details[row['path']] = client.get('/api/assistant/note', params={'path': row['path']}).json()
            for child in row['children']:
                visit(child)
        visit(detail['tree'])
    fixture = {'index': client.get('/api/assistant').json(), 'details': details,
               'note': str(note.relative_to(root)), 'child': details[str(context.relative_to(root))]['path'],
               'series': str(series.relative_to(root)), 'note_id': note.stem, 'series_id': series.stem}
    checks = r'''
const assert=(ok,message)=>{if(!ok)throw new Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw new Error('Timed out: '+fn)};
const W=LabWorkspaceDocuments, assistant={workspace_id:'__assistant__',vault:'__assistant__'};
let scope=assistant, minutes=1440, pendingDetail=null, now=Number(sessionStorage.getItem('recent-now')||1700000000000);
Date.now=()=>now;
const calls=[], notices=[];
window.explorerToast=message=>notices.push(message);
window.fetch=async(url,options={})=>{
 assert(!options.method,'Opening history must not write documents or links');
 const u=new URL(url,'https://lab.example'); calls.push(u.pathname);
 let result;
 if(u.pathname==='/api/assistant')result=FIX.index;
 else if(u.pathname==='/api/workspace-documents')result=[];
 else {
  if(pendingDetail)await pendingDetail;
  result=FIX.details[u.searchParams.get('path')];
 }
 return {ok:!!result,json:async()=>structuredClone(result||{detail:'Document missing'})};
};
W.configure({context:()=>scope,recentMinutes:()=>minutes});
const key=()=> 'lab.documents.recent.v1:'+scope.vault+'::'+scope.workspace_id;
const recent=()=>document.querySelector('[data-recent-documents]');
const rows=()=>[...recent().querySelectorAll('[data-terminal-document]')];
const ids=()=>rows().map(row=>row.dataset.terminalDocument);
const saved=()=>JSON.parse(localStorage.getItem(key())||'[]');
const open=async(kind,path)=>{now++;await AssistantView.openDocument(kind,path);};
const mount=()=>W.mount(scope,document.getElementById('sidebar'),true);
(async()=>{
 await mount();
 AssistantView.init({section:'documents'});
 await until(()=>document.querySelector('[data-assistant-document]'));
 assert(recent().nextElementSibling.hasAttribute('data-workspace-documents'),'Recently opened sits immediately above Linked documents');
 if(!sessionStorage.getItem('recent-reloaded')){
  assert(!rows().length,'unopened documents never enter history');
  await open('note',FIX.note);
  assert(ids().join()===FIX.note_id,'successful document opens enter history without a terminal link');
  assert(rows()[0].classList.contains('document-open'),'current document is highlighted');
  const timestamp=saved()[0].opened_at;
  now+=1000;await AssistantView.refresh();
  assert(saved()[0].opened_at===timestamp,'background refresh does not change opening time');
  await open('series',FIX.series);
  assert(ids().join()===[FIX.series_id,FIX.note_id].join(),'newest opening appears first');
  await open('note',FIX.child);
  assert(ids().join()===[FIX.note_id,FIX.series_id].join(),'opening a subtab updates its root document without duplicates');
  assert(saved()[0].path===FIX.note,'history stores the root path rather than the subtab path');
  sessionStorage.setItem('recent-now',String(now));
  sessionStorage.setItem('recent-reloaded','yes');location.reload();return;
 }
 assert(ids().join()===[FIX.note_id,FIX.series_id].join(),'history and ordering survive a real page reload');
 assert(!recent().querySelector('.workspace-document-remove'),'recent shortcuts never unlink workspace references');
 const stable=JSON.stringify(saved());
 await AssistantView.openDocument('note','missing');AssistantView.closeDocument();
 assert(JSON.stringify(saved())===stable,'failed opens never enter history');
 let release;pendingDetail=new Promise(resolve=>release=resolve);
 const opening=AssistantView.openDocument('note',FIX.note);
 AssistantView.closeDocument();release();await opening;pendingDetail=null;
 assert(JSON.stringify(saved())===stable,'cancelled asynchronous opens never enter history');
 rows()[1].querySelector('button').click();
 await until(()=>document.querySelector('#assistantExpandedHost #assistantDocumentModal.active')&&ids()[0]===FIX.series_id);
 assert(ids().join()===[FIX.series_id,FIX.note_id].join(),'keyboard activation reopens a recent document and moves it to the top');
 AssistantView.closeDocument();
 const button=rows()[1].querySelector('button');
 button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
 button.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:2}));
 button.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,detail:2}));
 await until(()=>document.querySelector('#assistantDocumentModal.active:not(.assistant-document-inline)'));
 assert(ids()[0]===FIX.note_id,'double-click reopens a recent document in the modal');
 AssistantView.closeDocument();
 const commandClick=new MouseEvent('click',{bubbles:true,cancelable:true,detail:1,button:0,metaKey:true});
 assert(!rows()[0].querySelector('button').dispatchEvent(commandClick),'Command-click consumes the native document-entry action');
 await until(()=>document.querySelector('#assistantDocumentModal.active:not(.assistant-document-inline)'));
 await new Promise(resolve=>setTimeout(resolve,350));
 assert(!AssistantView.isInlineDocument(),'Command-click opens a recent document in the modal without a later inline open');
 AssistantView.closeDocument();
 const renamed=structuredClone(FIX.index);
 Object.assign(renamed.documents.find(doc=>doc.id===FIX.note_id),{title:'Renamed <document>',path:'documents/renamed.md'});
 W.updateDocuments(renamed);
 assert(rows()[0].textContent.includes('Renamed <document>')&&!rows()[0].querySelector('document'),'renamed titles are refreshed and escaped');
 const transfer=new DataTransfer();
 rows()[0].querySelector('button span:last-child').dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:transfer}));
 assert(JSON.parse(transfer.getData('application/x-lab-file-path'))[0]===FIX.index.root+'/documents/renamed.md','drag uses the latest source path');
 assert(JSON.parse(transfer.getData('application/x-lab-assistant-document')).document_id===FIX.note_id,'drag preserves the stable document identity');
 const stored=saved();stored[0].opened_at=now-20*60000;stored[1].opened_at=now-60*60000;
 localStorage.setItem(key(),JSON.stringify(stored));minutes=15;await mount();
 assert(!rows().length,'15-minute window hides older openings');
 minutes=60;await mount();assert(rows().length===2,'a larger window restores history and includes the cutoff');
 now+=1;await mount();assert(rows().length===1,'openings expire without changing saved timestamps');
 const deleted=structuredClone(renamed);deleted.documents=deleted.documents.filter(doc=>doc.id!==FIX.note_id);
 W.updateDocuments(deleted);assert(!rows().length,'deleted documents disappear when the index refreshes');
 W.updateDocuments(FIX.index);minutes=1440;
 scope={workspace_id:'demo',vault:'one'};await mount();assert(!rows().length,'a workspace has its own history');
 await open('series',FIX.series);assert(ids().join()===FIX.series_id,'workspace document opening is recorded');
 scope={workspace_id:'demo',vault:'two'};await mount();assert(!rows().length,'same workspace name in another vault has separate history');
 scope=assistant;await mount();assert(rows().length===2,'returning to Assistant restores its own history');
 const other=structuredClone(FIX.index);other.root='/different/assistant';W.updateDocuments(other);
 assert(!rows().length,'history never leaks into a different Assistant database');
 W.updateDocuments(FIX.index);
 scope={workspace_id:'bad-storage',vault:'one'};
 localStorage.setItem(key(),'{broken');await mount();assert(!rows().length,'corrupt browser storage does not break the sidebar');
 localStorage.setItem(key(),JSON.stringify([null,{document_id:'invalid'}]));await mount();
 assert(!rows().length,'malformed history rows are ignored');
 // Preserve the session's history if storage writes are denied or full.
 const setItem=Storage.prototype.setItem;
 Storage.prototype.setItem=function(name,value){if(name.startsWith('lab.documents.recent.'))throw Error('Quota');return setItem.call(this,name,value)};
 await open('note',FIX.note);await open('series',FIX.series);
 assert(ids().join()===[FIX.series_id,FIX.note_id].join(),'in-memory history survives unavailable storage');
 Storage.prototype.setItem=setItem;
 scope={workspace_id:'bounded',vault:'one'};await mount();
 const documents=Array.from({length:12},(_,i)=>({id:'doc-'+i,title:'Document '+i,path:'documents/'+i+'.md'}));
 W.updateDocuments({root:FIX.index.root,documents});
 for(const doc of documents){now++;W.openDocument({assistant_root:FIX.index.root,document_id:doc.id,title:doc.title,path:doc.path});}
 assert(rows().length===10&&saved().length===10&&ids()[0]==='doc-11'&&ids().at(-1)==='doc-2','history stays bounded and retains the newest documents');
 // Another window's opening is immediately reflected without replacing linked rows.
 const linked=document.querySelector('[data-workspace-documents]');
 localStorage.setItem(key(),JSON.stringify([{assistant_root:FIX.index.root,document_id:'doc-0',path:'documents/0.md',opened_at:now}]));
 window.dispatchEvent(new StorageEvent('storage',{key:key()}));
 assert(ids().join()==='doc-0'&&document.querySelector('[data-workspace-documents]')===linked,'cross-window updates preserve the existing linked section');
 localStorage.removeItem(key());window.dispatchEvent(new StorageEvent('storage',{key:key()}));
 assert(!rows().length,'cleared browser history clears recent rows');
 assert(!calls.some(path=>path.startsWith('/api/term')||path.includes('document-terminal')),'history never starts or attaches a terminal');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>' + (STATIC / path).read_text() + '</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'js/lib/workspace-documents.js', 'js/views/assistant.js', 'js/views/assistant-tasks.js'])
    css = '\n'.join((STATIC / path).read_text() for path in [
        'css/lab-shell.css', 'css/workspace-documents.css', 'css/assistant-tasks.css'])
    page = tmp_path / 'recent.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>' + css + '</style><body class="assistant-active">'
                    '<div id="repoTabs"></div><div class="layout"><aside class="sidebar" id="sidebar"><section data-workspace-documents></section></aside>'
                    '<div id="content" class="main"></div></div><pre id="result">PENDING</pre>' + scripts +
                    '<script>const FIX=' + json.dumps(fixture).replace('</', '<\\/') + ';' + checks + '</script>')
    profile = tmp_path / 'profile'
    browser = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
                                '--no-default-browser-check', '--allow-file-access-from-files',
                                '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile), page.as_uri(),
                                 str(tmp_path / 'dom.html'), str(tmp_path / 'recent.png')], capture_output=True,
                                text=True, timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path / 'dom.html').read_text()
        result = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
        assert result and result[1] == 'PASS', result[1] if result else html[-2000:]
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=5)
