"""Held native workspace drags displace neighbours without persisting a move."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import time

import pytest

from .test_frontend_terminal_ui import _js_between, LAB_APP, LAB_SHELL_CSS, INDEX_HTML

MOTION = (LAB_APP.parent / 'lib/tab-drag-preview.js').read_text()
WORKSPACES = _js_between('  function workspaceTabsLoadOrder()', '  async function workspaceTabsClose(')


def test_motion_module_is_loaded_before_the_app():
    assert '/static/js/lib/tab-drag-preview.js?v={{ ASSET_V }}' in INDEX_HTML.read_text()


def test_native_workspace_preview_slides_retargets_cancels_and_persists(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    setup = r'''
const rows=['a','b','c','d'].map((id,i)=>({path:'/'+id+'/workspaces/demo',name:'demo',display_name:['Research','Research','Analysis and notes','Build'][i],vault:id,tab_open:true,is_workspace:true}));
let workspaceTabsAll=rows,currentWorkspace=rows[0],workspaceTabsOrder=JSON.parse(localStorage.getItem('order')||'null')||rows.map(w=>w.path);
let workspaceTabsOrderReady=true,workspaceTabsOrderLoad=null,workspaceTabsOrderSave=Promise.resolve(),workspaceTabsDragId=null;
const SELF_WORKSPACE_ID='__self__',ASSISTANT_WORKSPACE_ID='__assistant__',LAB_IS_ADMIN=true,tabBlocked={};
const _vaultForWorkspace=w=>({name:w.vault,color:'#58a6ff'}),_workspaceDisplayName=w=>w.display_name;
const workspaceTabsOpenIds=()=>rows.map(w=>w.path),fetchRepos=async()=>rows,vaultRefreshWorkspaceResources=()=>{};
const goToProductivity=()=>{},goToAssistant=()=>{},goToWorkspace=()=>{},openVaultWorkspaceMenu=()=>{},_workspaceVaultId=w=>w.vault;
window.errors=[];addEventListener('error',e=>errors.push(e.error?.stack||e.message));addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const writes=[];window.fetch=async(url,options)=>{if(options){const order=JSON.parse(options.body).order;writes.push(order);localStorage.setItem('order',JSON.stringify(order));}return {ok:true,json:async()=>workspaceTabsOrder}};
workspaceTabsRender();
window.originalNodes=[...document.querySelectorAll('.workspace-tab[data-kind=workspace]')];
const previewOrder=()=>[...document.querySelector('#workspaceTabs').children].filter(n=>!n.classList.contains('workspace-drag-source')&&(n.dataset.kind==='workspace'||n.classList.contains('workspace-drop-preview'))).map(n=>n.classList.contains('workspace-drop-preview')?workspaceTabsDragId:n.dataset.key);
document.body.dataset.ready='true';
'''
    page='<!doctype html><meta charset="utf-8"><style>'+LAB_SHELL_CSS.read_text()+'''body{background:#161b22}.workspace-tabs{height:54px;width:1200px;flex:none;margin:20px}</style><body class="workspace-active"><div id="workspaceTabs" class="workspace-tabs"></div><div id="outside" style="height:500px"></div><script>'''+MOTION+WORKSPACES+setup+'</script>'
    (tmp_path/'fixture.html').write_text(page)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(tmp_path)))
    Thread(target=server.serve_forever,daemon=True).start()
    profile=tmp_path/'chrome'
    process=subprocess.Popen([chrome,'--headless=new','--no-first-run','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    driver=r'''
const fs=require('node:fs');
(async()=>{
 const assert=(v,m)=>{if(!v)throw Error(m)},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const [port]=fs.readFileSync(process.argv[1]+'/DevToolsActivePort','utf8').split('\n');
 const tab=await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(tab.webSocketDebuggerUrl),pending=new Map();let seq=0,dragData;
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Input.dragIntercepted')dragData=m.params.data;if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||'Browser error');return r.result.value;}
 async function ready(){for(let i=0;i<150;i++){if(await evaluate('document.body?.dataset.ready==="true"'))return;await sleep(20)}throw Error('Startup: '+await evaluate('errors.join("\\n")'));}
 const key=id=>'/'+id+'/workspaces/demo',selector=id=>'.workspace-tab[data-key="'+key(id)+'"]';
 const order=()=>evaluate(`workspaceTabsOrder.map(path=>path.split('/')[1]).join('')`),preview=()=>evaluate(`previewOrder().map(path=>path.split('/')[1]).join('')`);
 const point=(id,before)=>evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector(id))}),r=LabTabDragPreview.rect(n);return {x:r.left+r.width*${before?'.2':'.8'},y:r.top+r.height/2}})()`);
 async function start(id){dragData=null;const p=await point(id,true);await send('Input.setInterceptDrags',{enabled:true});await send('Input.dispatchMouseEvent',{type:'mouseMoved',...p});await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',buttons:1,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:p.x+25,y:p.y+3,button:'left',buttons:1});for(let i=0;i<100&&!dragData;i++)await sleep(10);assert(dragData,'trusted drag starts');}
 let lastPoint;
 async function over(id,before=false){lastPoint=await point(id,before);for(const type of ['dragEnter','dragOver','dragOver'])await send('Input.dispatchDragEvent',{type,...lastPoint,data:dragData});}
 async function end(cancel=false){await send('Input.dispatchDragEvent',{type:cancel?'dragCancel':'drop',...lastPoint,data:dragData});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...lastPoint,button:'left',clickCount:1});await send('Input.setInterceptDrags',{enabled:false});await sleep(10);}
 await send('Emulation.setDeviceMetricsOverride',{width:1500,height:900,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:process.argv[2]});await ready();
 assert(await order()==='abcd','initial workspace order');
 await start('a');await over('c');
 assert(await preview()==='bcad'&&await order()==='abcd','held drag previews exact placement without changing order');
 assert(await evaluate(`writes.length===0&&originalNodes.every(n=>n.isConnected)&&document.querySelectorAll('.workspace-drop-preview').length===1`),'hover retains real nodes and makes no writes');
 const sample=await evaluate(`(()=>{const n=originalNodes[1],a=n.getAnimations().find(a=>a.id==='lab-tab-drag-shift');return {moving:!!a,delta:n.getBoundingClientRect().left-LabTabDragPreview.rect(n).left}})()`);
 assert(sample.moving&&Math.abs(sample.delta)>1,'neighbour visibly slides into the preview gap: '+JSON.stringify(sample));
 await sleep(65);
 const next=await evaluate(`originalNodes[1].getBoundingClientRect().left-LabTabDragPreview.rect(originalNodes[1]).left`);
 assert(Math.abs(next)<Math.abs(sample.delta),'neighbour approaches its destination smoothly');
 await over('b',true);assert(await preview()==='abcd','rapid reversal restores the earlier preview position');
 assert(await evaluate(`writes.length===0&&document.querySelectorAll('.workspace-drop-preview').length===1`),'retargeting keeps one preview without saving');
 await over('d');assert(await preview()==='bcda','preview can cross several neighbours');
 fs.writeFileSync(process.argv[1]+'/../workspace-held.png',Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await end(true);await sleep(220);
 assert(await order()==='abcd'&&await evaluate(`writes.length===0&&!document.querySelector('.workspace-drop-preview,.workspace-drag-source')&&originalNodes.every(n=>n.isConnected&&n.getAnimations().every(a=>a.id!=='lab-tab-drag-shift'))`),'cancel restores original layout, nodes and saved order');
 await start('a');await over('c');const intended=await preview();await end();await evaluate('workspaceTabsOrderSave');
 assert(await order()===intended&&await evaluate('writes.length')===1,'release saves exactly the final preview once');
 await evaluate(`document.body.dataset.ready='false'`);await send('Page.reload');await ready();assert(await order()==='bcad','workspace drop persists across reload with duplicate names across vaults');
 await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
 await start('d');await over('b',true);
 assert(await preview()==='dbca'&&await evaluate(`[...document.querySelectorAll('.workspace-tab')].every(n=>n.getAnimations().every(a=>a.id!=='lab-tab-drag-shift'))&&writes.length===0`),'reduced motion shows placement without sliding or writes');
 await end(true);assert(await order()==='bcad'&&await evaluate('errors.length')===0,'reduced-motion cancellation preserves order without browser errors');
 ws.close();console.log('PASS');
})().catch(e=>{console.error(e.stack);process.exit(1)});
'''
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline,'Chrome did not start'
            time.sleep(.05)
        result=subprocess.run(['node','-e',driver,str(profile),f'http://127.0.0.1:{server.server_port}/fixture.html'],capture_output=True,text=True,timeout=35)
        assert result.returncode==0,result.stdout+result.stderr
    finally:
        process.terminate();process.wait(timeout=10);server.shutdown();server.server_close()
