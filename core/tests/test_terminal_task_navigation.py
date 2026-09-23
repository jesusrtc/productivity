"""Terminal task links open an exact task without changing terminal/workspace state."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401
from .test_frontend_terminal_ui import _js_between, _run_node

ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'core/src/core/static'


def test_task_badges_escape_titles_and_carry_stable_identity():
    source=_js_between('  function _termTaskLinkHtml(', '  function _termInstallTaskLinkActions(')
    result=_run_node(source+'''
function termSessEsc(value){return String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');}
const link={document_id:'doc',assistant_root:'/assistant',task_id:'child',title:'Call <Alex> "today"'};
process.stdout.write(JSON.stringify({html:_termTaskLinkHtml(link,true),empty:_termTaskLinkHtml(null)}));
''')
    assert result['empty']==''
    assert 'Call &lt;Alex>' in result['html'] and '&quot;today&quot;' in result['html']
    assert 'term-task-link-pill' in result['html'] and 'data-terminal-task-open=' in result['html']


def test_terminal_task_modal_browser(client, owned_tasks, tmp_path):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):pytest.skip('Chrome and Node required')
    root,note,context,child,*_=owned_tasks
    path=str(note.relative_to(root))
    detail=client.get('/api/assistant/note',params={'path':path}).json()
    details={}
    def visit(row):
        details[row['path']]=client.get('/api/assistant/note',params={'path':row['path']}).json()
        for child in row['children']:visit(child)
    visit(detail['tree'])
    target=next(task for task in detail['document_tasks']['tasks'] if task['title']=='Find number')
    fixture={'index':client.get('/api/assistant').json(),'details':details,'target':target,'path':path,
             'other_tab':str(child.relative_to(root)),
             'link':{'document_id':note.stem,'task_id':target['id'],'title':target['title'],
                     'assistant_root':str(root),'path':path}}
    checks=r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw new Error('Timed out: '+fn)};
function termSessEsc(value){return String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');}
const notices=[],calls=[];let activated=0,renamed=0;
const explorerToast=message=>notices.push(message),_termHideSessionTooltip=()=>{};
window.LabDocumentTerminal={open:detail=>calls.push(['open',detail.path]),focusTask:id=>calls.push(['focus',id]),close:()=>{},updateRoot:()=>{},decorate:()=>{}};
window.fetch=async(url,options={})=>{
 assert(!options.method||options.method==='GET','task navigation must never start or mutate a terminal');
 const u=new URL(url,'https://example.test');
 const result=u.pathname==='/api/assistant'?FIX.index:FIX.details[u.searchParams.get('path')];
 return {ok:!!result,json:async()=>structuredClone(result||{detail:'Missing record'})};
};
document.querySelector('#pill').innerHTML='Renamed terminal '+_termTaskLinkHtml(FIX.link,true);
document.querySelector('#identity').innerHTML=_termTaskLinkHtml(FIX.link);
document.querySelector('#pill').addEventListener('click',()=>activated++);
document.querySelector('#pill').addEventListener('dblclick',()=>renamed++);
document.querySelector('#pill').addEventListener('keydown',()=>activated++);
_termInstallTaskLinkActions();
const prefix='lab.assistant.tasks.v1:'+FIX.index.root+':'+FIX.link.document_id;
localStorage.setItem(prefix+':completed','false');
localStorage.setItem(prefix+':collapsed',JSON.stringify([FIX.target.parent_id]));
localStorage.setItem('lab.assistant.last-tab.v1:'+FIX.index.root+':'+FIX.link.document_id,FIX.other_tab);
const focused=()=>document.querySelector(`[data-task="${FIX.target.id}"].is-terminal-target`);
(async()=>{
 // Assistant was never initialized: open over a normal workspace terminal.
 document.querySelector('#pill button').click();
 await until(()=>focused());
 assert(document.querySelector('#assistantDocumentModal.active'),'same document modal opens');
 assert(document.querySelector('[data-record-path].active')?.dataset.recordPath===FIX.path,'inherited task tab wins over last visited subtab');
 assert(focused().getClientRects().length&&document.activeElement===focused(),'completed nested task is revealed and focused');
 assert(!document.querySelector('[data-show-all]').matches('[aria-pressed=true]'),'does not turn on show all');
 assert(localStorage.getItem(prefix+':completed')==='false','completed visibility preference remains unchanged');
 assert(localStorage.getItem(prefix+':collapsed')===JSON.stringify([FIX.target.parent_id]),'saved collapsed preferences preserved');
 assert(calls.at(-1)[0]==='focus'&&calls.at(-1)[1]===FIX.target.id,'associated terminal task selected');
 assert(!activated&&!renamed&&document.body.classList.contains('workspace-active'),'terminal selection and workspace stay put');
 assert(document.getElementById('content').textContent==='Current workspace content','workspace content is preserved');
 // A user can collapse the revealed branch again.
 document.querySelector(`[data-collapse="${FIX.target.parent_id}"]`).click();
 assert(!focused(),'manual disclosure overrides reveal');
 AssistantView.closeDocument();
 document.querySelector('#identity button').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
 await until(()=>focused());
 assert(!activated&&!renamed,'keyboard activation stays out of terminal handlers');
 AssistantView.closeDocument();
 // Ordinary document links still open the remembered content tab.
 await AssistantView.openLinkedTask({...FIX.link,task_id:null});
 assert(document.querySelector('#assistantDocumentModal.active')&&calls.at(-1)[1]===null,'document links work without a task');
 let rejected=false;
 try{await AssistantView.openLinkedTask({...FIX.link,assistant_root:'/different-database'})}catch(error){rejected=error.message.includes('different Assistant')}
 assert(rejected,'never open an ID in another database');
 AssistantView.closeDocument();
 document.querySelector('#identity button').click();await until(()=>focused());
 assert(!notices.length,'no navigation errors');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    helpers=_js_between('  function _termTaskLinkHtml(', '  function _termSessionIdentityHtml(')
    scripts='\n'.join('<script>'+(STATIC/name).read_text()+'</script>' for name in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','js/views/assistant.js','js/views/assistant-tasks.js'])
    page=tmp_path/'navigation.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>:root{--accent:#58a6ff;--text-primary:#e6edf3;--bg-secondary:#161b22;--border:#30363d}body{background:#0d1117;color:#e6edf3}'+(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/assistant-tasks.css').read_text()+'</style><body class="workspace-active"><div id="content">Current workspace content</div><div class="term-panel term-sessions-full"><div class="term-sessions"><span id="pill" class="sess"></span></div><div id="identity"></div></div><pre id="result">PENDING</pre>'+scripts+'<script>'+helpers+'\nconst FIX='+json.dumps(fixture).replace('</','<\\/')+';\n'+checks+'</script>')
    profile=tmp_path/'profile'
    browser=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        subprocess.run(['node',str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'navigation.png')],check=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        html=(tmp_path/'dom.html').read_text();result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
        assert result and result[1]=='PASS',result[1] if result else html[-2000:]
    finally:
        browser.terminate();browser.wait(timeout=10)
