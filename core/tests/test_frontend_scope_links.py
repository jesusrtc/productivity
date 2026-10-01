"""Late reads and repeated mounts preserve the active checkout's link ownership."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest


from .test_frontend_terminal_ui import ROOT, _run_node


def test_scope_links_ignore_late_reads_and_keep_cached_buttons_clickable():
    module = (ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result = _run_node(r"""
const replies={},calls=[],opened=[];
const window={LabExternalLinks:{open:async url=>opened.push({url})},
  AssistantView:{openLinkedTask:async(link,options)=>{if(options.isCurrent())opened.push({id:link.document_id,tab:link.tab_id,whole:options.wholeDocument})}}};
const fetch=url=>new Promise(resolve=>replies[decodeURIComponent(url.split('path=')[1])]=data=>resolve({ok:true,json:async()=>data}));
const host=path=>({dataset:{scopeLinks:path},isConnected:true,paintCount:0,buttons:[],
  set innerHTML(value){this.paintCount++;this.edit={};this.buttons=Array.from(value.matchAll(/data-scope-link="(\d+)"/g),m=>({dataset:{scopeLink:m[1]}}));},
  querySelector(){return this.edit;},querySelectorAll(){return this.buttons;}});
""" + module + """
(async()=>{
  let active='/old';const old=host('/old'),current=host('/new');
  const first=window.LabScopeLinks.mount(old,()=>active==='/old');
  active='/new';old.isConnected=false;
  const second=window.LabScopeLinks.mount(current,()=>active==='/new');
  replies['/old']({links:[{kind:'external',url:'https://old.invalid'}],revision:'old'});
  replies['/new']({links:[{kind:'internal',document_id:'doc',tab_id:'tab',title:'Doc / Tab'},
    {kind:'internal',document_id:'doc',tab_id:null,title:'Doc'},
    {kind:'external',url:'https://new.invalid'}],revision:'new'});
  await Promise.all([first,second]);
  await window.LabScopeLinks.mount(current,()=>active==='/new');
  for(const button of current.buttons)await button.onclick();
  active='/another';await current.buttons[0].onclick();
  process.stdout.write(JSON.stringify({oldPaint:old.paintCount,newPaint:current.paintCount,opened}));
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1});
""")
    assert result == {'oldPaint':0,'newPaint':1,'opened':[
        {'id':'doc','tab':'tab','whole':False}, {'id':'doc','tab':None,'whole':True}, {'url':'https://new.invalid'}]}


@pytest.mark.parametrize('viewport', [1440, 390])
def test_internal_document_browser_keeps_targets_through_search_and_late_reads(tmp_path, viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    static=ROOT/'core/src/core/static'
    setup=r'''
const assert=(v,message)=>{if(!v)throw Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
const q=s=>document.querySelector('.scope-links-dialog '+s);
const click=s=>q(s).click();
let confirms=0,mode='slow',releaseSecond,saved;
window.confirm=()=>{confirms++;return true};
const documents=[{id:'one',title:'Roadmap',path:'/notes/one.md',search_text:'Delivery roadmap'},
 {id:'two',title:'Incident guide',path:'/notes/two.md',search_text:'Operations handbook'}];
let links=[{id:'existing',type:'internal-docs',document_id:'one',tab_id:'deep',label:'Plan'}];
const types=[{id:'internal-docs',name:'Internal docs',kind:'internal'},{id:'jira',name:'Jira',kind:'external'}];
window.fetch=async(url,options={})=>{
 const parsed=new URL(url,'https://lab.test');let data;
 if(parsed.pathname==='/api/scope-links'){
  if(options.method==='PUT'){saved=JSON.parse(options.body);links=saved.links;}
  data={links,types,revision:'revision'};
 }else if(parsed.pathname==='/api/assistant')data={configured:true,root:'/assistant',documents};
 else if(parsed.pathname==='/api/assistant/note'){
  const second=parsed.searchParams.get('path').includes('two');
  if(second&&mode==='slow')await new Promise(resolve=>releaseSecond=resolve);
  if(second&&mode==='error')return {ok:false,json:async()=>({detail:'Could not read document'})};
  data={tree:{children:second?[{id:'incident',title:'Incident steps'}]:[{id:'implementation',title:'Implementation',children:[{id:'deep',title:'Detailed rollout'}]}]}};
 }else throw Error('Unexpected API '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
'''
    checks=r'''
(async()=>{
 const loaded=()=>q('[data-link-card]')&&!q('[data-link-card]')._targetLoading;
 const open=async()=>{await LabScopeLinks.edit('/trees/topic',()=>true,{kind:'worktree',label:'project/topic'});await until(loaded)};
 const save=async()=>{q('form').requestSubmit();await until(()=>!document.querySelector('.scope-links-dialog'))};
 const fits=()=>{const dialog=document.querySelector('.scope-links-dialog'),r=dialog.getBoundingClientRect();assert(r.left>=0&&r.right<=innerWidth+1&&dialog.scrollWidth<=dialog.clientWidth+1,'dialog fits viewport');for(const el of dialog.querySelectorAll('.scope-document-columns'))assert(el.scrollWidth<=el.clientWidth+1,'document list fits viewport')};
 await open();
 assert(q('[data-document-picker]').hidden&&q('[data-document-destination]').textContent==='Tab · Detailed rollout','saved nested tab appears as compact target');
 click('[data-change-document]');fits();
 const search=q('[data-document-search]');search.value='operations';search.dispatchEvent(new Event('input',{bubbles:true}));
 assert(q('[data-document="two"]')&&!q('[data-document="one"]'),'search covers document content and hides nonmatches including chosen doc');
 search.value='missing';search.dispatchEvent(new Event('input',{bubbles:true}));assert(!q('[data-document]'),'empty search has no stale rows');
 search.dispatchEvent(new Event('change',{bubbles:true}));click('[data-close]');assert(confirms===0,'searching and viewing do not create unsaved metadata changes');
 await open();click('[data-change-document]');
 q('[data-document-search]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));
 assert(document.activeElement===q('[data-document="one"]'),'search arrow moves focus to native document button');
 click('[data-document="two"]');await until(()=>releaseSecond);
 q('form').requestSubmit();await until(()=>q('[data-message]').textContent.startsWith('Wait for'));
 assert(!saved,'save while document tabs load preserves prior saved metadata');
 click('[data-document="one"]');await until(loaded);releaseSecond();await new Promise(r=>setTimeout(r,20));
 assert(q('[data-tab="deep"]')&&!q('[data-tab="incident"]'),'late document read cannot overwrite selected document tabs');
 click('[data-tab="deep"]');click('[data-finish-document]');await save();
 assert(saved.path==='/trees/topic'&&saved.links[0].id==='existing'&&saved.links[0].document_id==='one'&&saved.links[0].tab_id==='deep','nested tab identity and exact checkout save');
 // Missing saved tabs require a deliberate new target, never a silent fallback.
 links[0].tab_id='removed';await open();
 assert(q('[data-target-message]').textContent.includes('unavailable')&&q('[data-finish-document]').disabled&&!q('[data-document-picker]').hidden,'missing saved tab remains an error with picker open');
 q('form').requestSubmit();await until(()=>q('[data-message]').textContent.includes('unavailable'));
 click('[data-tab=""]');click('[data-finish-document]');await save();
 assert(saved.links[0].tab_id===null,'explicit whole document choice clears missing tab');
 await open();click('[data-change-document]');mode='error';click('[data-document="two"]');await until(()=>q('[data-retry-tabs]'));
 assert(q('[data-finish-document]').disabled,'failed tab read cannot confirm a destination');
 mode='immediate';click('[data-retry-tabs]');await until(loaded);assert(q('[data-tab="incident"]'),'failed detail fetch can retry');
 click('[data-tab=""]');click('[data-finish-document]');await save();
 assert(saved.links[0].document_id==='two'&&saved.links[0].tab_id===null,'new document saves whole-document identity');
 await open();click('[data-change-document]');fits();
 document.getElementById('result').textContent='PASS document search, keyboard, exact targets, late reads, missing tabs, retries, responsive layout';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    page=tmp_path/'links.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#8b949e;--text-dim:#6e7681;--border:#30363d;--accent:#58a6ff}'+(static/'css/lab-shell.css').read_text()+'</style><pre id="result">PENDING</pre><script>'+setup+'</script><script>'+(static/'js/lib/scope-links.js').read_text()+'</script><script>'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'links.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
