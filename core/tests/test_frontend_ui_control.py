"""Real CLI → HTTP → authenticated browser → shared mutation end to end."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from threading import Thread
import time

from fastapi.responses import HTMLResponse
import pytest
import uvicorn

from lab import objectives

STATIC=Path(__file__).resolve().parents[1]/'src/core/static'


def test_cli_operates_link_modal_drag_workspace_and_terminal_label(client,monorepo,seed_workspace,tmp_path):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    folder=seed_workspace()
    data=objectives.mutate(monorepo,'demo',{'type':'create','name':'CLI project'})
    oid=data['objectives'][0]['id']
    data=objectives.mutate(monorepo,'demo',{'type':'resource','objective_id':oid,'kind':'link','title':'Reference','url':'https://example.com/original'})
    rid=data['objectives'][0]['resources'][0]['id']
    objectives.mutate(monorepo,'demo',{'type':'asset-star','objective_id':oid,'resource_id':rid,'starred':True})
    data=objectives.mutate(monorepo,'demo',{'type':'task','objective_id':oid,'title':'CLI task'})
    tid=data['objectives'][0]['tasks'][0]['id']
    from core.routes import term
    term._upsert_workspace_session(monorepo,'demo',{'name':'ui-shell','kind':'terminal','cwd':str(folder)})
    app_source=(STATIC/'js/lab-app.js').read_text()
    patch_links=app_source[app_source.index('  async function _termPatchLinks('):app_source.index('  window.LabTaskTerminalBridge =')]
    navigation=app_source[app_source.index('  function goToWorkspace('):app_source.index('  // Navigate to a workspace by its id')]
    resize_start=app_source.index('  function _termInitSessionResize()')
    resize=app_source[resize_start:app_source.index('\n  }\n',resize_start)+5]
    hooks=app_source[app_source.index('  if(LAB_IS_ADMIN)window.LabUiControl?.start('):]
    setup=r'''
const LAB_IS_ADMIN=true,currentVaultId=null;let currentWorkspace={name:'demo',path:FIX.folder,is_workspace:true},workspacesList=[currentWorkspace],_workspaceDocPath=null;
const _workspaceVaultId=()=>null,_swapViewState=()=>{},_settleWorkspaceHistory=()=>{},fetchRepos=async()=>workspacesList;
const selectRepo=async path=>{currentWorkspace=workspacesList.find(w=>w.path===path);document.querySelector('#view-status').textContent=path;};
let termSessions=[{name:'ui-shell-live',logical_name:'ui-shell',label:null,state:'running'}];
let termCurrentSession='ui-shell-live';const termCurrentWorkspaceId='demo',requestSubmissions=[],_termRequestSubmitted=(...parts)=>requestSubmissions.push(parts);const pasted=[],sent=[],termXterm={modes:{bracketedPasteMode:true},paste:text=>pasted.push(text)},termWS={readyState:WebSocket.OPEN,send:value=>sent.push(JSON.parse(value))},_termActivateTab=async name=>{termCurrentSession=name};
const _termLinkContext=()=>({workspaceId:'demo',vaultId:null}),_termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>null;
const _termSessionsCache=new Map(),_termSessionsKey=(w,v)=>w+'::'+v,termRenderSessionList=()=>document.querySelector('#terminal-label').textContent=termSessions[0].label||'Shell',_termRenderActiveSessionHeader=()=>{};
let termSessionWidth=180,termSessionOrientation='vertical';const _TERM_SESSION_WIDTH_KEY='cli-test-width',_termSessionWidthBounds=()=>({min:160,max:220}),_termApplySessionView=()=>{document.querySelector('#termSessionList').style.width=termSessionWidth+'px'};
window.explorerToast=message=>{document.querySelector('#notice').textContent=message};
window.LabExternalLinks={open:()=>Promise.resolve(true)};
LabObjectives.connect({context:()=>({workspace_id:'demo',path:FIX.folder}),refreshTabs:()=>{},readyContent:()=>Promise.resolve(),prepareCenter:()=>{}});
LabObjectives.load().then(()=>LabObjectives.selectObjective(FIX.oid));
'''
    page='<!doctype html><meta charset="utf-8"><style>'+(STATIC/'css/workspace-objectives.css').read_text()+'body{background:#0d1117;color:white;display:flex}#sidebar{width:350px}#content{flex:1}</style><aside id="sidebar"><section data-objectives-sidebar></section></aside><main id="content"></main><section><button id="tasks" onclick="LabObjectives.renderTasks()">Tasks</button><button id="native" onclick="const value=prompt(\'Name\');if(value!==null)document.querySelector(\'#native-value\').textContent=value">Native prompt</button><span id="native-value"></span><span id="terminal-label">Shell</span><span id="view-status"></span><p id="notice"></p></section>'
    page+='<script>const FIX='+json.dumps({'folder':str(folder),'oid':oid})+';</script>'
    page+=''.join('<script>'+(STATIC/'js/lib'/name).read_text()+'</script>' for name in ('workspace-objectives.js','ui-control.js'))
    page+='<div id="termPanel"><div id="termSessionSwitcher" class="term-tabs-open"><div id="termSessionList" style="width:180px">Terminal rail</div><div id="termSessionsResizer" role="separator" tabindex="0" aria-label="Resize terminal tabs" style="width:5px;height:30px"></div></div></div>'
    page+='<script>'+setup+patch_links+navigation+resize+'_termInitSessionResize();'+hooks+'</script>'
    app=client.app
    @app.get('/_cli-test',include_in_schema=False)
    def fixture_page(): return HTMLResponse(page)
    listener=socket.socket();listener.bind(('127.0.0.1',0))
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='off'))
    thread=Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    profile=tmp_path/'chrome'
    process=subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver=r'''
const fs=require('node:fs'),{execFileSync}=require('node:child_process');
(async()=>{
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const target=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let seq=0;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description);return r.result.value};
 const cli=(...args)=>JSON.parse(execFileSync(process.argv[3],['-m','lab',...args],{encoding:'utf8',env:{...process.env,LAB_URL:process.argv[2]}}));
 const assert=(v,m)=>{if(!v)throw Error(m)};
 await send('Page.navigate',{url:process.argv[2]+'/login'});
 for(let i=0;i<100;i++){if(await evaluate(`location.pathname==='/login'&&document.readyState==='complete'`))break;await new Promise(r=>setTimeout(r,30));}
 await evaluate(`fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'admin',password:'admin'})}).then(r=>{if(!r.ok)throw Error('login')})`);
 await send('Page.navigate',{url:process.argv[2]+'/_cli-test'});
 let view;
 for(let i=0;i<200;i++){view=cli('ui','clients').find(c=>c.url.endsWith('/_cli-test'));if(view&&await evaluate(`!!document.querySelector('[data-objective-resource]')`))break;await new Promise(r=>setTimeout(r,30));}
 assert(view,'registered browser view');
 const ui=(...args)=>cli('ui','--client',view.id,...args);
 const inspect=()=>ui('inspect');
 const control=label=>{const row=inspect().controls.find(c=>c.label===label);assert(row,'control '+label);return row.selector};
 ui('contextmenu','[data-objectives-sidebar] [data-objective-resource="'+process.argv[4]+'"]');
 ui('click',control('Edit'));
 assert(inspect().dialogs.some(d=>d.title==='Edit link'),'CLI opens real modal');
 ui('fill','[data-objective-link-field=url]','https://example.com/cli-edited');
 ui('click','[data-save-objective-link]');ui('wait','[data-link-details-status]','--text','Saved');
 let data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');
 assert(data.objectives[0].resources.find(r=>r.id===process.argv[4]).url==='https://example.com/cli-edited','same saved resource');
 ui('key','Escape');assert(!inspect().dialogs.length,'CLI Escape closes modal');
 let promptResult=ui('click','#native');assert(promptResult.native_dialogs[0].requires_answer,'unanswered prompt returns without blocking');
 ui('click','#native','--prompt','CLI name');assert(await evaluate(`document.querySelector('#native-value').textContent==='CLI name'`),'prompt answer is scoped to the action');
 ui('rename-tab','ui-shell','Review renamed');assert(await evaluate(`document.querySelector('#terminal-label').textContent==='Review renamed'`),'terminal rename uses real shared metadata handler');
 ui('paste','First line\nSecond line','--terminal','ui-shell');assert(await evaluate(`pasted.at(-1)==='First line\\nSecond line'&&sent.length===0`),'terminal paste retains bracketed text without submitting');
 await evaluate(`termXterm.modes.bracketedPasteMode=false`);ui('paste','One\nTwo');assert(await evaluate(`pasted.at(-1)==='One Two'&&sent.length===0`),'unbracketed multiline paste stays unsent');
 ui('paste','Explicit command','--submit');assert(await evaluate(`sent.length===1&&sent[0].data==='\\r'&&requestSubmissions.length===1&&requestSubmissions[0][1]==='demo'`),'only explicit submit sends Enter');
 ui('command','pointer-drag','--json',JSON.stringify({selector:'#termSessionsResizer',x:20,y:0}));assert(await evaluate(`termSessionWidth===200&&localStorage.getItem(_TERM_SESSION_WIDTH_KEY)==='200'`),'CLI resize uses and saves the real terminal rail handler');
 ui('click','#tasks');ui('drag','[data-objectives-sidebar] [data-objective-resource="'+process.argv[4]+'"]','.objective-task-row[data-task-id="'+process.argv[5]+'"]');
 for(let i=0;i<100;i++){data=cli('api','call','GET','/api/objectives','--query','workspace_id=demo');if(data.objectives[0].tasks[0].assets?.some(a=>a.resource_id===process.argv[4]))break;await new Promise(r=>setTimeout(r,30));}
 assert(data.objectives[0].tasks[0].assets.some(a=>a.resource_id===process.argv[4]),'CLI drag uses task asset drop handler');
 const opened=cli('workspace','open','demo','--client',view.id);assert(opened.workspace==='demo'&&await evaluate(`document.querySelector('#view-status').textContent===FIX.folder&&new URL(location.href).searchParams.get('workspace')===FIX.folder`),'workspace command awaits real in-page navigation');
 ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        for _ in range(150):
            if (profile/'DevToolsActivePort').is_file() and server.started: break
            time.sleep(.05)
        import sys
        result=subprocess.run(['node','-e',driver,str(profile),base,sys.executable,rid,tid],capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        assert 'PASS' in result.stdout
        assert term._get_workspace_sessions(monorepo,'demo')[0]['label']=='Review renamed'
    finally:
        process.terminate();process.wait(timeout=10)
        server.should_exit=True;thread.join(timeout=10);listener.close()
