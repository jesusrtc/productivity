"""Rendered mission/chat interactions with the actual frontend module."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_mission_chat_task_evidence_and_permissions_in_browser(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required for rendered interaction coverage')
    checks = r'''
const assert=(value,message)=>{if(!value)throw Error(message)};
const until=async fn=>{for(let i=0;i<200;i++){if(fn())return;await new Promise(r=>setTimeout(r,10))}throw Error('Timeout '+fn)};
const task={id:'t',mission_id:'m',parent_id:null,title:'Analyze growth',instruction:'Read input.csv and execute analysis.ipynb',context:'Use Lab Jupyter',status:'review',result:'Growth: 200%',blocker:'Waiting for review',next_reminder:1900000000,active_run:null};
const asset={id:'a',task_id:'t',mission_id:'m',kind:'file',target:'analysis.ipynb',title:'Analysis notebook',role:'support',origin:'agent',run_id:'r'};
const state={provider:'claude',model:null,providers:[{id:'codex',available:true},{id:'copilot',available:true},{id:'claude',available:true}],settings:{enabled:true,max_workers:5,reminder_seconds:7200,timezone:'UTC',provider:null,model:null},missions:[{id:'m',title:'Explain growth',objective:'Investigate the increase',status:'active'}],tasks:[task],runs:[{id:'r',role:'executor',status:'completed'}],messages:[{id:'u',role:'user',content:'Analyze growth',status:'handled',created:1}],schedules:[],memory:[],permissions:[],assets:[asset]};
const detail={task,runs:[{id:'r',provider:'claude',status:'completed',created:1,prompt:'EXACT ORIGINAL ASSIGNMENT <script>bad()</script>',argv:['claude','-p']}],assets:[asset],permissions:[],events:[{seq:600,kind:'provider-stdout',at:1,body:{text:'Last event'}}]};
let sent=[], failSend=false, notebookRenders=0, olderCalls=0;
window.fetch=async(url,options={})=>{
 const u=new URL(url,'http://localhost');let result=state;
 if(u.pathname.endsWith('/tasks/t'))result=detail;
 else if(u.pathname.endsWith('/tasks/__coordinator__'))result={...detail,coordinator:true,task:{...task,id:'__coordinator__',title:'Workspace coordinator',mission_id:null}};
 else if(u.pathname.endsWith('/assets/a'))result={asset,kind:'notebook',cells:[{source:'print(200)',outputs:[{content:'200'}]}]};
 else if(u.pathname.endsWith('/events')){olderCalls++;result={events:[{seq:1,kind:'assignment',at:1,body:{prompt:'Original assignment'}}]};}
 else if(u.pathname.endsWith('/messages')){sent.push(JSON.parse(options.body));if(failSend)return {ok:false,json:async()=>({detail:'Temporary failure'})};result={id:'sent'};}
 else if(u.pathname.endsWith('/actions')){const a=JSON.parse(options.body).actions[0];if(a.type==='task-approve'){task.status='completed';task.blocker='';}else if(a.type==='permission-respond'){assert(a.option_id==='once','one-time option');detail.permissions[0].status='decided';}result={results:[]};}
 return {ok:true,json:async()=>structuredClone(result)};
};
(async()=>{
 LabAgentic.connect({ready:async()=>{},renderNotebook:(cells,target)=>{notebookRenders++;target.innerHTML='<pre data-notebook-output>'+cells[0].outputs[0].content+'</pre>'}});
 await LabAgentic.open(document.getElementById('content'),{workspace_id:'demo',path:'/demo',vault:'test'});
 assert(document.querySelectorAll('.agentic-chat').length===1,'one workspace chat');
 document.querySelector('[data-coordinator-inspect]').click();await until(()=>document.querySelector('[data-task-heading]')?.textContent.includes('Workspace coordinator'));
 assert(document.querySelector('[data-task-controls]').hidden,'coordinator has no task lifecycle controls');
 document.querySelector('[data-task-tab="assignment"]').click();assert(document.querySelector('[data-task-body]').textContent.includes('EXACT ORIGINAL ASSIGNMENT'),'coordinator assignment visible');
 document.querySelector('[data-task-close]').click();
 document.querySelector('[data-agentic-task="t"]').click();await until(()=>document.querySelector('[data-task-heading]')?.textContent.includes('Analyze growth'));
 const dialog=document.querySelector('.agentic-task-dialog'),chat=document.querySelector('.agentic-chat');
 assert(dialog.getBoundingClientRect().right<=chat.getBoundingClientRect().left,'modal stays alongside chat');
 document.querySelector('[data-task-tab="assignment"]').click();
 assert(document.querySelector('[data-task-body]').textContent.includes('EXACT ORIGINAL ASSIGNMENT'),'exact assignment visible');
 assert(!document.querySelector('[data-task-body] script'),'assignment is escaped');
 document.querySelector('[data-task-tab="activity"]').click();document.querySelector('[data-events-earlier]').click();
 await until(()=>document.querySelector('[data-task-body]').textContent.includes('Original assignment'));assert(olderCalls===1,'earlier activity accessible');
 document.querySelector('[data-task-tab="files"]').click();document.querySelector('[data-agentic-asset="a"]').click();
 await until(()=>document.querySelector('[data-notebook-output]'));assert(notebookRenders===1,'native notebook rendering adapter used');
 const input=document.querySelector('[data-agentic-input]');input.value='Follow up while preview is open';input.dispatchEvent(new Event('input'));input.focus();
 await LabAgentic.refresh(true);assert(document.activeElement===input&&input.value.startsWith('Follow up'),'chat remains responsive during preview refresh');
 document.querySelector('[data-preview-back]').click();document.querySelector('[data-task-tab="result"]').click();
 document.querySelector('[data-task-control="approve"]').click();await until(()=>document.querySelector('[data-task-heading]').textContent.includes('Completed'));
 task.status='blocked';task.active_run='r2';task.blocker='Tool permission';detail.permissions=[{id:'p',status:'pending',request:{toolCall:{title:'Write report',rawInput:{fileName:'/demo/report.md'}},options:[{optionId:'once',kind:'allow_once',name:'Allow once'},{optionId:'always',kind:'allow_always',name:'Always allow'}]}}];
 await LabAgentic.refresh(true);assert(document.querySelectorAll('[data-permission]').length===1,'only one-time permission choices');
 assert(!document.querySelector('[data-task-control="resume"]'),'waiting process cannot launch duplicate');
 document.querySelector('[data-permission]').click();await until(()=>document.querySelector('[data-task-body]').textContent.includes('Decision saved'));
 document.querySelector('[data-task-close]').click();failSend=true;document.querySelector('[data-agentic-compose]').requestSubmit();await until(()=>sent.length===1&&!document.querySelector('[type=submit]').disabled);
 const draft=input.value;assert(draft.startsWith('Follow up'),'failed send preserves draft');
 input.value='Changed followup';input.dispatchEvent(new Event('input'));failSend=false;document.querySelector('[data-agentic-compose]').requestSubmit();await until(()=>sent.length===2&&input.value==='');
 assert(sent[0].request_id!==sent[1].request_id,'edited request gets a new idempotency identity');
 input.value='Saved draft';input.dispatchEvent(new Event('input'));
 await LabAgentic.open(document.getElementById('content'),{workspace_id:'second',path:'/second',vault:'test'});
 assert(document.querySelector('[data-agentic-input]').value==='','workspace drafts isolated');
 await LabAgentic.open(document.getElementById('content'),{workspace_id:'demo',path:'/demo',vault:'test'});
 assert(document.querySelector('[data-agentic-input]').value==='Saved draft','draft survives navigation');
 document.getElementById('content').replaceChildren(document.createElement('article'));
 await until(()=>!document.body.classList.contains('agentic-workspace-open'));
 await LabAgentic.refresh(true);assert(!document.querySelector('.agentic-workspace'),'file navigation releases the mission view');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>' + (STATIC / path).read_text() + '</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'js/lib/agentic-workspace.js'])
    page = tmp_path / 'agentic.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>' + (STATIC / 'css/lab-shell.css').read_text() +
                    (STATIC / 'css/agentic-workspace.css').read_text() + '</style><div class="main" id="content"></div>'
                    '<pre id="result">PENDING</pre>' + scripts + '<script>' + checks.replace('</', '<\\/') + '</script>')
    profile = tmp_path / 'chrome-profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                                '--allow-file-access-from-files', '--user-data-dir=' + str(profile),
                                '--remote-debugging-port=0', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([node, str(ROOT / 'scripts/chrome-dump-auth.mjs'), str(profile), page.as_uri(),
                                 str(tmp_path / 'dom.html'), str(tmp_path / 'agentic.png')], capture_output=True, text=True,
                                timeout=25, env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path / 'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
    assert result and result[1] == 'PASS', result[1] if result else html[-1000:]
