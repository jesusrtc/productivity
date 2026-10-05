"""Native demo gestures keep shared/task context distinct from archive."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest

STATIC = Path(__file__).resolve().parents[2] / 'core/src/core/static'


def test_objectives_demo_buckets_and_context_drag(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(STATIC)))
    Thread(target=server.serve_forever, daemon=True).start()
    profile = tmp_path / 'chrome'
    process = subprocess.Popen([chrome, '--headless=new', '--no-first-run', '--remote-debugging-port=0',
                                '--user-data-dir=' + str(profile), 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    driver = r'''
const fs=require('node:fs');
(async()=>{
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map(),errors=[],requests=[];let sequence=0,dragData=null;
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser assertion');return r.result.value;}
 async function point(selector){return evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n)throw Error('Missing '+${JSON.stringify(selector)});n.scrollIntoView({block:'nearest'});const b=n.getBoundingClientRect();return{x:b.x+Math.min(20,b.width/2),y:b.y+b.height/2}})()`);}
 async function click(selector,button="left"){const p=await point(selector);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button,clickCount:1});}
 async function drag(source,selector){const a=await point(source);dragData=null;await send('Input.setInterceptDrags',{enabled:true});await send('Input.dispatchMouseEvent',{type:'mouseMoved',...a});await send('Input.dispatchMouseEvent',{type:'mousePressed',...a,button:'left',buttons:1,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:a.x+30,y:a.y+3,button:'left',buttons:1});for(let i=0;i<100&&!dragData;i++)await new Promise(r=>setTimeout(r,10));assert(dragData,'native drag data');const b=await point(selector);for(const type of ['dragEnter','dragOver','drop'])await send('Input.dispatchDragEvent',{type,...b,data:dragData});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...b,button:'left',clickCount:1});await send('Input.setInterceptDrags',{enabled:false});return dragData;}
 await send('Runtime.enable');await send('Network.enable');await send('Emulation.setDeviceMetricsOverride',{width:1768,height:1200,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});
 for(let i=0;i<200;i++){if(await evaluate('!!document.querySelector("[data-task=validate]")'))break;await new Promise(r=>setTimeout(r,20));}
 assert(await evaluate(`document.querySelectorAll('.ob-nav-tab').length===2&&!document.querySelector('.ob-focus-slot')`),'two production-style tabs');
 assert(await evaluate(`JSON.stringify([...document.querySelectorAll('[data-overview]>[data-bucket]')].map(n=>n.dataset.bucket))===JSON.stringify(['unassigned','objective','tasks','task'])`),'sidebar bucket order');
 assert(await evaluate(`!document.querySelector('.ob-sidebar-task input,.ob-sidebar-task [aria-label^="Edit "]')&&!document.querySelector('.ob-sidebar-task.child')`),'sidebar tasks navigate without edits and start collapsed');
 assert(await evaluate(`[...document.querySelectorAll('.ob-sidebar-task')].every(n=>n.firstElementChild.classList.contains('ob-task-status')&&n.lastElementChild.hasAttribute('data-task-icon'))`),'checkbox status left and terminal icon right');
 assert(await evaluate(`document.querySelector('[data-bucket=unassigned] [data-asset="worktree::triage"]')&&!document.querySelector('.ob-explorer [data-asset^="worktree::"]')&&document.querySelectorAll('.ob-worktree-roots .ob-fixed-root').length===2`),'unassigned worktree is an asset; explorer keeps only two roots');
 await drag('[data-bucket=unassigned] [data-item=metrics-query]','.ob-sidebar-task[data-task=validate]');
 await evaluate(`window.taskAssetsPosition=()=>document.querySelector('[data-bucket=task]').getBoundingClientRect().top+document.querySelector('[data-overview]').scrollTop+window.scrollY;window.reservedAssetsTop=taskAssetsPosition()`);
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name');
 assert(await evaluate(`Math.abs(taskAssetsPosition()-reservedAssetsTop)<1`),'assets stay put when the largest task unfolds');
 assert(await evaluate(`!!document.querySelector('.cm-editor')&&document.querySelector('[data-bucket=task] [data-asset=metrics-query]')&&!document.querySelector('[data-bucket=unassigned] [data-asset=metrics-query]')`),'native editor and task attachment remove unassigned');
 assert(await evaluate(`document.querySelector('[data-task-icon=validate]')?.childElementCount===0&&document.querySelector('[data-current-objective] .ob-task-default-icon')?.textContent==='✅'&&document.querySelector('[data-terminal=t1] .ob-task-default-icon')?.textContent==='✅'`),'ordinary attachment leaves the right icon empty and keeps default tab/terminal status');
 assert(await evaluate(`document.querySelectorAll('.ob-sidebar-task.child').length===2&&document.querySelector('.ob-task-mode-title > span:last-child').textContent==='Validate phone parsing'`),'selected task expands only its children and has a mode header');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name','right');
 assert(await evaluate(`document.querySelectorAll('.ob-task-status-menu [role=menuitemradio]').length===3&&document.querySelector('.ob-task-status-menu [aria-checked=true]').dataset.setTaskStatus==='done'`),'secondary click opens task status menu');
 await click('.ob-task-status-menu [data-set-task-status=in_progress]');
 assert(await evaluate(`document.querySelector('.ob-sidebar-task[data-task=validate] .ob-task-status').textContent==='🟡'&&document.querySelector('[data-current-objective] .ob-task-default-icon').textContent==='🟡'&&document.querySelector('[data-terminal=t1] .ob-task-default-icon').textContent==='🟡'&&!document.querySelector('.ob-task-completion input').checked`),'work in progress updates sidebar, tab and terminal');
 assert(await evaluate(`[...document.querySelectorAll('.ob-sidebar-task.child .ob-task-status')].every(n=>n.dataset.done==='true')`),'work in progress preserves child completion');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name','right');await click('.ob-task-status-menu [data-set-task-status=todo]');
 assert(await evaluate(`document.querySelector('.ob-sidebar-task[data-task=validate] .ob-task-status').textContent==='⬜'&&[...document.querySelectorAll('.ob-sidebar-task.child .ob-task-status')].every(n=>n.dataset.done==='false')`),'undo keeps box and clears children');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name','right');await click('.ob-task-status-menu [data-set-task-status=done]');
 assert(await evaluate(`document.querySelector('.ob-task-completion input').checked&&!document.querySelector('.ob-task-status-menu')`),'completed closes menu and restores completion');
 await click('.ob-task-completion input');
 assert(await evaluate(`!document.querySelector('.ob-task-completion input').checked&&[...document.querySelectorAll('.ob-sidebar-task.child .ob-task-status')].every(n=>n.dataset.done==='false')`),'parent completion changes from task-mode header');
 assert(await evaluate(`document.querySelector('.ob-sidebar-task[data-task=validate] .ob-task-status').textContent==='⬜'&&document.querySelector('[data-task-icon=validate]').childElementCount===0&&document.querySelector('[data-terminal=t1] .ob-task-default-icon').textContent==='⬜'`),'status changes do not add a duplicate right icon');
 await click('.ob-sidebar-task[data-task=validate-todo-1] .ob-task-name');
 assert(await evaluate(`Math.abs(taskAssetsPosition()-reservedAssetsTop)<1`),'assets stay put on subtask navigation');
 await click('.ob-task-completion input');
 assert(await evaluate(`document.querySelector('.ob-task-completion input').checked&&document.querySelector('.ob-sidebar-task[data-task=validate] .ob-task-status').dataset.done==='false'`),'subtask completion is independent of unfinished sibling');
 const subtask=await drag('.ob-sidebar-task[data-task=validate-todo-1] .ob-task-name','[data-console=t1] textarea');
 const subRefs=JSON.parse(subtask.items.find(i=>i.mimeType==='application/x-lab-reference').data);
 const subPrompt=subtask.items.find(i=>i.mimeType==='text/plain').data;assert(subPrompt.startsWith('Context:\nObjective: \"SMS recovery\"')&&subPrompt.includes('Parent task: \"Validate phone parsing\"')&&subPrompt.includes('This task: \"Verify recovery behavior\"')&&subPrompt.includes('Work only on This task: \"Verify recovery behavior\"')&&subPrompt.includes('Task specification:')&&subPrompt.includes('SQL file:')&&subPrompt.includes('Notebook:')&&subPrompt.includes('read-only unless also listed under This task'),'subtask drag is a labelled, scope-limited prompt');assert(await evaluate(`document.querySelector('[data-console=t1] textarea').value===${JSON.stringify(subPrompt)}`),'demo pastes captured task prompt without running');
 for(const expected of ['/demo/workspace/objectives/sms/Incident notes#tab=validate-details','/demo/workspace/objectives/sms/Incident notes#tab=validate-todo-1-details','/demo/workspace/objectives/sms/Verification volume.ipynb','/demo/client/worktrees/sdui/fix-phone','/demo/client/worktrees/sdui/fix-phone/queries/volume.sql'])assert(subRefs.includes(expected),'ancestor context '+expected);
 assert(new Set(subRefs).size===subRefs.length&&subRefs.indexOf('/demo/workspace/objectives/sms/Incident notes')<subRefs.indexOf('/demo/workspace/objectives/sms/Incident notes#tab=validate-details')&&subRefs.indexOf('/demo/workspace/objectives/sms/Incident notes#tab=validate-details')<subRefs.indexOf('/demo/workspace/objectives/sms/Incident notes#tab=validate-todo-1-details'),'objective then parent then subtask context');
 await drag('[data-terminal=t2]','.ob-sidebar-task[data-task=validate-todo-1]');await click('[data-terminal=t2]');
 assert(await evaluate(`document.querySelector('.ob-task-mode-title > span:last-child').textContent==='Verify recovery behavior'`),'reverse terminal association opens exact subtask');
 await click('.ob-sidebar-task[data-task=rollout] .ob-task-name');
 assert(await evaluate(`Math.abs(taskAssetsPosition()-reservedAssetsTop)<1`),'assets stay put when a smaller task unfolds');
 assert(await evaluate(`document.querySelectorAll('.ob-sidebar-task.child').length===1&&!document.querySelector('.ob-sidebar-task[data-task=validate-todo-1]')`),'another parent folds previous children');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name');
 await drag('[data-bucket=task] [data-asset=metrics-query] .ob-resource','[data-task-icon=validate]');
 assert(await evaluate(`document.querySelector('[data-task-icon=validate] .ft-sql')&&document.querySelector('[data-current-objective] .ft-sql')&&document.querySelector('[data-terminal=t1] .ft-sql')`),'asset icon drop propagates to task, active tab and associated terminal');
 await click('[data-bucket=task] [data-asset=metrics-query] .ob-star');
 assert(await evaluate(`document.querySelector('[data-bucket=objective] [data-asset=metrics-query] .ob-star').getAttribute('aria-pressed')==='true'&&document.querySelector('[data-bucket=task] [data-asset=metrics-query]')`),'star shares asset without losing task association');
 await click('[data-bucket=objective] [data-asset=metrics-query] .ob-star');
 assert(await evaluate(`!document.querySelector('[data-bucket=objective] [data-asset=metrics-query]')&&document.querySelector('[data-bucket=task] [data-asset=metrics-query]')`),'unstar preserves task asset');
 await click('[data-bucket=task] [data-asset=volume] .ob-resource');
 assert(await evaluate(`document.querySelector('.ob-task-mode-title > span:last-child').textContent==='Validate phone parsing'&&document.querySelector('.ob-cell')&&document.querySelector('.ob-close-task')`),'task header and completion survive browsing task notebook');
 await click('[data-bucket=unassigned] .ob-bucket-title');
 assert(await evaluate(`document.querySelector('[data-reader] h2').textContent==='Tasks'&&!document.querySelector('.ob-close-task')`),'Unassigned opens middle task list');
 await drag('[data-terminal=t2]','[data-reader] .ob-task-row[data-task=release]');
 assert(await evaluate(`document.querySelector('[data-terminal=t2]').getAttribute('aria-label').includes('Verify recovery behavior')`),'central task rows reject terminal association drops');
 await drag('[data-bucket=unassigned] [data-item=thread]','[data-reader] .ob-task-row[data-task=validate]');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name');
 assert(await evaluate(`!!document.querySelector('[data-bucket=task] [data-asset=thread]')`),'Unassigned asset attaches through middle task list');
 await drag('[data-terminal=t2]','[data-bucket=task] [data-asset=metrics-query] .ob-resource');await click('[data-terminal=t2]');
 assert(await evaluate(`document.querySelector('[data-reader] h2').textContent==='queries/volume.sql'&&!document.querySelector('.ob-close-task')`),'reverse terminal drop associates exact file in first column');
 await click('[data-terminal=t1]');
 const data=await drag('.ob-sidebar-task[data-task=validate] .ob-task-name','[data-console=t1] textarea');
 const refs=JSON.parse(data.items.find(i=>i.mimeType==='application/x-lab-reference').data);
 const prompt=data.items.find(i=>i.mimeType==='text/plain').data;assert(prompt.includes('This task: \"Validate phone parsing\"')&&!prompt.includes('Parent task:'),'top-level prompt does not invent a parent');for(const ref of refs)assert(prompt.split('\n').filter(line=>line.endsWith(' — '+ref)).length===1,'prompt emits each exact reference once');assert(await evaluate(`document.querySelector('[data-console=t1] textarea').value.endsWith(${JSON.stringify(prompt)})`),'task prompt appended without replacing existing terminal draft');
 for(const expected of ['https://app.slack.com/client/demo/incident','/demo/workspace/objectives/sms/Incident notes#tab=validate-details','/demo/workspace/objectives/sms/Verification volume.ipynb','/demo/client/worktrees/sdui/fix-phone','/demo/client/worktrees/sdui/fix-phone/queries/volume.sql'])assert(refs.includes(expected),'complete task context '+expected);
 assert(new Set(refs).size===refs.length&&!refs.some(r=>r.includes('Old incident notes')||r.includes('Unparseable')),'deduplicated context excludes archive and other tasks');
 assert(await evaluate(`document.querySelector('[data-console=t1] textarea').value.includes('queries/volume.sql')&&document.querySelector('.ob-console-log').textContent==='Objectives demo terminal · help lists simulated commands.'`),'console drag pastes without running');
 await drag('[data-bucket=task] [data-asset=volume] .ob-resource','[data-bucket=objective]');
 const common=await drag('.ob-sidebar-task[data-task=validate] .ob-task-name','[data-console=t1] textarea');
 const commonRefs=JSON.parse(common.items.find(i=>i.mimeType==='application/x-lab-reference').data);
 assert(commonRefs.filter(r=>r.endsWith('Verification volume.ipynb')).length===1,'shared and task membership deduplicate');
 await drag('[data-bucket=objective] [data-asset=volume] .ob-resource','.ob-archive');
 const archived=await drag('.ob-sidebar-task[data-task=validate] .ob-task-name','[data-console=t1] textarea');
 assert(!JSON.parse(archived.items.find(i=>i.mimeType==='application/x-lab-reference').data).some(r=>r.endsWith('Verification volume.ipynb')),'archive excluded from agent context');
 await click('.ob-archive>summary');await drag('[data-bucket=archive] [data-asset=volume] .ob-resource','[data-bucket=unassigned]');
 assert(await evaluate(`!!document.querySelector('[data-bucket=unassigned] [data-asset=volume]')`),'archive recovery keeps source');
 await drag('[data-bucket=unassigned] [data-item=volume]','[data-task-icon=validate]');
 assert(await evaluate(`document.querySelector('[data-task-icon=validate] .ft-nb')&&document.querySelector('[data-bucket=task] [data-asset=volume]')&&!document.querySelector('[data-bucket=unassigned] [data-asset=volume]')`),'icon drop also attaches a previously unassigned asset');
 await click('[data-bucket=objective] [data-asset=incident] .ob-expand');
 await click('[data-bucket=objective] [data-asset=incident] .ob-subtab-line .ob-star');
 assert(await evaluate(`!!document.querySelector('[data-bucket=objective] [data-asset="incident::timeline"]')`),'document child has its own exact shared star');
 const starredTab=await drag('.ob-sidebar-task[data-task=validate] .ob-task-name','[data-console=t1] textarea');
 assert(JSON.parse(starredTab.items.find(i=>i.mimeType==='application/x-lab-reference').data).includes('/demo/workspace/objectives/sms/Incident notes#tab=timeline'),'starred subtab retains exact context reference');
 await click('.ob-explorer>summary');
 assert(await evaluate(`document.querySelectorAll('.ob-worktree-roots .ob-fixed-root').length===2&&!document.querySelector('.ob-explorer .ob-star,.ob-explorer .ob-asset-tools,.ob-worktree-roots .ob-star,.ob-explorer [data-asset^="worktree::"]')`),'explorer files and folders have no stars or asset controls, only fixed roots');
 await click('.ob-sidebar-task[data-task=release] .ob-task-name');
 await drag('[data-terminal=t2]','[data-bucket=task] [data-asset="worktree::checkpoint"] .ob-resource');
 assert(await evaluate(`document.querySelector('[data-terminal=t2]').getAttribute('aria-label').includes('checkpoint/verification')`),'reverse association accepts a left worktree');
 await drag('.ob-sidebar-task[data-task=validate] .ob-task-name','[data-terminal=t2]');await click('[data-terminal=t2]');
 assert(await evaluate(`document.querySelector('[data-reader] h2').textContent==='Validate phone parsing'&&document.querySelector('[data-bucket=task] [data-asset=metrics-query]')`),'task terminal association restores selected task assets');
 await click('.ob-close-task');assert(await evaluate(`document.querySelector('[data-reader] h2').textContent==='Tasks'&&!document.querySelector('[data-bucket=task] [data-asset]')`),'task close clears selection');
 await drag('[data-bucket=unassigned] [data-asset="worktree::triage"] .ob-resource','.ob-sidebar-task[data-task=rollout]');
 assert(await evaluate(`!document.querySelector('[data-bucket=unassigned] [data-asset="worktree::triage"]')&&!document.querySelector('[data-bucket=task] [data-asset="worktree::triage"]')`),'worktree assigned to another task disappears from Unassigned');
 await click('.ob-sidebar-task[data-task=rollout] .ob-task-name');
 assert(await evaluate(`document.querySelector('[data-bucket=task] [data-asset="worktree::triage"]')&&!document.querySelector('[data-bucket=task] [data-asset="worktree::phone-fix"]')`),'task selection changes the worktree assets');
 await click('[data-bucket=task] [data-asset="worktree::triage"] .ob-star');
 await click('.ob-sidebar-task[data-task=validate] .ob-task-name');
 assert(await evaluate(`document.querySelector('[data-bucket=objective] [data-asset="worktree::triage"]')&&document.querySelector('[data-bucket=task] [data-asset="worktree::phone-fix"]')`),'shared worktree remains available across tasks');
 await drag('[data-bucket=objective] [data-asset="worktree::triage"] .ob-resource','[data-bucket=unassigned]');
 assert(await evaluate(`document.querySelector('[data-bucket=unassigned] [data-asset="worktree::triage"]')`),'worktree can return to Unassigned without losing its source');
 const whole=await drag('[data-bucket=objective] .ob-section-heading span','[data-console] textarea');
 const wholeModel=JSON.parse(whole.items.find(i=>i.mimeType==='application/x-lab-task-context').data),wholeRefs=JSON.parse(whole.items.find(i=>i.mimeType==='application/x-lab-reference').data),wholePrompt=whole.items.find(i=>i.mimeType==='text/plain').data;
 assert(wholeModel.kind==='objective'&&wholeModel.tasks.length===11&&wholePrompt.includes('This objective: "SMS recovery"')&&wholePrompt.includes('Subtask of "Validate phone parsing": "Verify recovery behavior"')&&!wholePrompt.includes('Work only on This task:'),'whole Objective names its tasks, subtasks and scope');
 for(const ref of ['/demo/workspace/objectives/sms/.objective.json','/demo/workspace/objectives/sms','/demo/client/worktrees/sdui/fix-phone','/demo/client/worktrees/recovery/triage','/demo/workspace/objectives/sms/Task details.md#tab=release-details','https://demo.atlassian.net/browse/PHONE-26080'])assert(wholeRefs.includes(ref),'whole Objective reference '+ref);
 assert(!wholeRefs.some(ref=>ref.includes('Old incident notes'))&&new Set(wholeRefs).size===wholeRefs.length&&wholeRefs.every(ref=>wholePrompt.split('\n').filter(line=>line.endsWith(' — '+ref)).length===1),'whole Objective excludes archive and defines each reference once');
 assert(await evaluate(`document.querySelector('[data-console] textarea').value.endsWith(${JSON.stringify(wholePrompt)})&&document.querySelector('[data-console] .ob-console-log').textContent==='Objectives demo terminal · help lists simulated commands.'`),'whole Objective prompt is unsent');
 await click('[data-all-objectives]');assert(await evaluate(`document.querySelectorAll('[data-slot]').length===5`),'five ordered focus slots');
 const emptyObjective=await drag('[data-objective=followup-study]','[data-slot="0"]');
 assert(JSON.parse(emptyObjective.items.find(i=>i.mimeType==='application/x-lab-task-context').data).tasks.length===0,'empty Objective still provides context while moving slots');
 assert(await evaluate(`document.querySelector('[data-slot="0"] strong').textContent==='Follow-up investigation'&&document.querySelector('[data-slot="1"] strong').textContent==='SMS recovery'&&document.querySelector('[data-objective=release-study]').textContent.includes('Parked')`),'slot insertion shifts and parks fifth');
 assert(!errors.length,'no browser exceptions: '+errors.join('\n'));assert(!requests.some(url=>url.includes('/api/')||url.startsWith('ws:')),'demo never uses workspace/terminal APIs');
 ws.close();console.log('PASS');
})().catch(error=>{console.error(error.stack);process.exit(1)});
'''
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline, 'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run(['node', '-e', driver, str(profile),
                                 f'http://127.0.0.1:{server.server_port}/demos/objectives/index.html'],
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'PASS' in result.stdout
    finally:
        process.terminate()
        process.wait(timeout=10)
        server.shutdown()
        server.server_close()
