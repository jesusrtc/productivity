"""Standard Documents: task edits, stars, content editing, tab creation and memory."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import pytest
from lab import assistant_records as records, assistant_tasks as tasks
from .test_assistant_document_tasks import owned_tasks, legacy_tasks

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT/'core/src/core/static'


def test_document_tasks_browser(client, owned_tasks, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root,note,context,child,series,meeting=owned_tasks
    fixture={name:str(path.relative_to(root)) for name,path in [('note',note),('context',context),('child',child),('series',series),('meeting',meeting)]}
    fixture['id']=note.stem
    config={p:p.read_bytes() for p in (root/'.assistant/dashboard').glob('*.json')}
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<500;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const click=selector=>{const el=document.querySelector(selector);assert(el,'Missing '+selector);el.click()};
const checked=id=>document.querySelector(`[data-check="${id}"]`);
const all=()=>document.querySelector('[data-show-all]').getAttribute('aria-pressed')==='true';
const saved=()=>until(()=>!AssistantTasks.busy()&&document.querySelector('.assistant-tasks-save-status')?.textContent==='Saved to document');
const taskData=async()=>fetch('/api/assistant/note?path='+encodeURIComponent(FIX.note)).then(r=>r.json());
const openTab=async path=>{click(`[data-record-path="${path}"]`);await until(()=>document.querySelector(`[data-record-path="${path}"].active`)&&!document.getElementById('assistantDocumentModal').hasAttribute('aria-busy'))};
const set=async(selector,value)=>{const input=document.querySelector(selector);assert(input,'Missing '+selector);input.value=value;input.dispatchEvent(new Event('change'));await saved()};
const add=async title=>{click('[data-add-task]');document.getElementById('assistantTaskTitle').value=title;document.querySelector('.assistant-tasks-task-form').requestSubmit();await saved();return (await taskData()).document_tasks.tasks.find(task=>task.title===title)};
window.confirm=()=>true;
window.alert=message=>{throw new Error(message)};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>document.querySelector('[data-dashboard-section="starred"] [data-assistant-document]'));
 assert(document.querySelector('[data-dashboard-edit]'),'saved dashboard still has its filter controls');
 await AssistantView.openDocument('note',FIX.note);
 await until(()=>document.querySelector('[data-document-tasks]'));
 if(sessionStorage.getItem('reloaded')){
   const deep=sessionStorage.getItem('deep');
   assert(document.querySelector(`[data-record-path="${deep}"].active`),'last nested tab survives a full reload');
   assert(!all(),'reopened scope starts with subtasks hidden');
   await openTab(FIX.context);
   const data=await taskData(),task=data.document_tasks.tasks.find(task=>task.title==='Renamed work');
   assert(task.status==='in_progress'&&task.priority==='P0'&&task.due==='2026-10-01'&&task.owner==='Jesus','task edits persist in file');
   click('[data-record-index]');
   document.getElementById('result').textContent='PASS';return;
 }
 await AssistantView.openDocument('meeting',FIX.meeting);
 assert(document.querySelector('[data-series-toggle]'),'migrated meeting retains series history navigation');
 click('[data-series-toggle]');
 assert(document.querySelector(`[data-series-document="${FIX.meeting}"]`),'series history includes its dated or undated member');
 await AssistantView.openDocument('note',FIX.note);
 assert(!document.querySelector('[data-metadata-field="track_task"]')&&!document.querySelector('[data-metadata-field="status"]'),'tabs no longer have task lifecycle controls');
 assert(document.querySelector('[data-record-index]').textContent.includes('Dashboard'),'normal document has a task dashboard');
 assert(!all(),'subtasks initially hidden');
 const initial=await taskData(),contextId=FIX.context.split('#tab=')[1],call=initial.document_tasks.tasks.find(task=>task.title==='Call Alex'),read=initial.document_tasks.tasks.find(task=>task.title==='Read source');
 assert(checked(call.id)&&!document.querySelector('[data-task="'+call.id+'"] .assistant-tasks-subtasks'),'direct tasks only by default');
 await openTab(FIX.context);
 assert(checked(contextId)&&!checked(read.id),'content tab shows own tasks only');
 click('[data-show-all]');assert(checked(read.id),'Show all includes descendant-tab work');
 click(`[data-task="${read.id}"] .assistant-tasks-task-label`);
 await until(()=>document.querySelector(`[data-record-path="${FIX.child}"].active`));
 assert(!all(),'task title opens owning tab with direct-task default');
 await openTab(FIX.context);
 const before=document.querySelectorAll('[data-record-path]').length;
 const work=await add('New work');
 assert(document.querySelectorAll('[data-record-path]').length===before,'adding a task creates no content tab');
 await set(`[data-status="${work.id}"]`,'in_progress');
 await set(`[data-priority="${work.id}"]`,'P0');
 click(`[data-task="${work.id}"] summary`);
 await set(`[data-task-title="${work.id}"]`,'Renamed work');
 await set(`[data-task-due="${work.id}"]`,'2026-10-01');
 await set(`[data-task-owner="${work.id}"]`,'Jesus');
 click(`[data-add-child="${work.id}"]`);
 document.getElementById('assistantTaskTitle').value='Confirm details';document.querySelector('.assistant-tasks-task-form').requestSubmit();await saved();
 click('[data-show-all]');
 const nested=(await taskData()).document_tasks.tasks.find(task=>task.title==='Confirm details');
 assert(checked(nested.id),'ordinary subtask is visible after Show all');
 click(`[data-check="${nested.id}"]`);await saved();
 assert(checked(work.id).checked,'all subtasks complete the parent task');
 assert(getComputedStyle(document.querySelector(`[data-task="${work.id}"] .assistant-tasks-task-label`)).textDecorationLine==='none','completed titles remain readable');
 click(`[data-check="${nested.id}"]`);await saved();
 await set(`[data-status="${work.id}"]`,'in_progress');
 click('[data-wip-only]');assert(checked(work.id)&&!checked(contextId),'WIP filter respects the selected tab');click('[data-wip-only]');
 const disposable=await add('Delete me');
 click(`[data-delete-task="${disposable.id}"]`);await saved();assert(!checked(disposable.id),'task deletion updates the file and view');
 const titles=['New peer','Nested peer'];window.prompt=()=>titles.shift();
 click('[data-record-root-tab]');await until(()=>document.getElementById('assistantModalTitle').textContent==='New peer'&&!document.getElementById('assistantDocumentModal').hasAttribute('aria-busy'));
 const peer=document.querySelector('[data-record-path].active').dataset.recordPath;
 click(`[data-record-subtab="${peer}"]`);await until(()=>document.getElementById('assistantModalTitle').textContent==='Nested peer'&&!document.getElementById('assistantDocumentModal').hasAttribute('aria-busy'));
 const deep=document.querySelector('[data-record-path].active').dataset.recordPath;sessionStorage.setItem('deep',deep);
 assert(document.querySelector(`[data-record-path="${peer}"]`).closest('li').querySelector(`[data-record-path="${deep}"]`),'new subtab remains nested under the selected parent');
 click('#assistantEditNote');
 const input=document.querySelector('textarea[aria-label="Note content"]');input.value='## Preserved editor\n\nNew nested notes.';input.dispatchEvent(new Event('input'));click('#assistantSaveNote');
 await until(()=>document.getElementById('assistantNoteStatus').textContent==='Saved');
 const edited=await fetch('/api/assistant/note?path='+encodeURIComponent(deep)).then(r=>r.json());
 assert(edited.body.includes('New nested notes.')&&edited.document_tasks.tasks.some(task=>task.title==='Renamed work'),'note save preserves tasks');
 click('#assistantModalMetadata [data-star-path]');await until(()=>document.querySelector('#assistantModalMetadata [data-star-path]').getAttribute('aria-pressed')==='false');
 click('#assistantModalMetadata [data-star-path]');await until(()=>document.querySelector('#assistantModalMetadata [data-star-path]').getAttribute('aria-pressed')==='true');
 AssistantView.closeDocument();await AssistantView.openDocument('note',FIX.note);
 assert(document.querySelector(`[data-record-path="${deep}"].active`),'reopening restores selected nested content tab');
 sessionStorage.setItem('reloaded','yes');location.reload();
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js','js/lib/markdown-content.js','js/views/assistant.js','js/views/assistant-tasks.js'])
    page = '<!doctype html><meta charset="utf-8"><style>body{background:#0d1117;color:#e6edf3;margin:0}'+(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/assistant-tasks.css').read_text()+'</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+'<script>const FIX='+json.dumps(fixture)+';</script><script>'+checks+'</script>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.startswith('/api/'):
                response = client.get(self.path); data = response.content; content_type = response.headers.get('content-type'); code=response.status_code
            elif self.path.startswith('/static/'):
                target = STATIC/self.path.split('?',1)[0].removeprefix('/static/')
                data=target.read_bytes(); content_type='text/css' if target.suffix=='.css' else 'text/javascript';code=200
            else:
                data=page.encode();content_type='text/html';code=200
            self.send_response(code);self.send_header('Content-Type',content_type);self.end_headers();self.wfile.write(data)
        def do_POST(self):
            response=client.request(self.command,self.path,json=json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
        do_PATCH=do_POST
        do_PUT=do_POST
    server=HTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline,'Chrome did not start'
            time.sleep(.05)
        subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),f'http://127.0.0.1:{server.server_port}/',str(tmp_path/'dom.html'),str(tmp_path/'tasks.png')],check=True,timeout=30)
        html=(tmp_path/'dom.html').read_text();result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
        assert result and result[1]=='PASS',result[1] if result else html[-2000:]
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close();thread.join(timeout=5)
    assert config=={path:path.read_bytes() for path in config}
    assert records.resolve(root,note.stem)[1]['starred']
    assert records.resolve(root,series.stem)[1]['starred']
    assert records.resolve(root,meeting.stem)[1]['starred']
