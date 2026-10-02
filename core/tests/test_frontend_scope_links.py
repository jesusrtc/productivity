"""Late reads and repeated mounts preserve the active checkout's link ownership."""

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import subprocess
import time
from threading import Thread

import pytest


from .test_frontend_terminal_ui import ROOT, _run_node


def test_scope_links_ignore_late_reads_and_keep_cached_buttons_clickable():
    module = (ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result = _run_node(r"""
const replies={},calls=[],opened=[];
const document={addEventListener(){},getElementById:()=>null};
const window={LabExternalLinks:{open:async (url,options)=>opened.push({url,...options})},
  AssistantView:{openLinkedTask:async(link,options)=>{if(options.isCurrent()){if(options.inline===true)throw Error('scope links must use the regular expanded document');opened.push({id:link.document_id,tab:link.tab_id,whole:options.wholeDocument})}}}};
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
        {'id':'doc','tab':'tab','whole':False}, {'id':'doc','tab':None,'whole':True}, {'url':'https://new.invalid/','clientOnly':True}]}


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
 const open=async()=>{await LabScopeLinks.edit('/trees/topic',()=>true,{kind:'worktree',label:'project/topic'});await until(loaded);assert(!q('select'),'no manual type dropdown');if(!q('[data-link-card]')._targetError)assert(q('[data-link-fields]').hidden,'valid saved links are compact');if(q('[data-link-fields]').hidden)click('[data-edit-link]')};
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


@pytest.mark.parametrize('viewport', [1440, 390])
def test_compact_link_editor_infers_icons_edits_and_saves_urls(tmp_path, viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    static=ROOT/'core/src/core/static'
    registry=json.loads((static/'link-services.json').read_text())
    setup=r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
const q=s=>document.querySelector('.scope-links-dialog '+s);
let saved,confirms=0,failSave=false;
window.confirm=()=>{confirms++;return true};
const links=[
 {id:'doc',kind:'internal',type:'internal-docs',document_id:'one',tab_id:'rollout',title:'Telesign Incident Room / SDUI changes'},
 {id:'google',kind:'external',type:'google-docs',label:'Telesign Incident Room - Track 3',url:'https://docs.google.com/document/d/example/edit'},
 {id:'discussion',kind:'external',type:'google-docs',label:'Malformed-phone PWR discussion',url:'https://company.atlassian.net/wiki/spaces/SDUI'},
 {id:'slack',kind:'external',type:'url',label:'Telesign incident Slack channel',url:'https://company.slack.com/archives/C123'},
 {id:'jira',kind:'external',type:'jira',label:'ACTIONITEM-26080 - Unparseable phone error',url:'https://jira.company.test/browse/ACTIONITEM-26080'},
 {id:'github',kind:'external',type:'url',label:'PRs for this branch (all states)',url:'https://github.com/org/repo/pulls'},
 {id:'grafana',kind:'external',type:'url',label:'Production Grafana dashboard',url:'https://grafana.company.test/d/errors'}];
const types=[{id:'internal-docs',name:'Internal docs',kind:'internal'},{id:'google-docs',name:'Google Docs',kind:'external'},{id:'jira',name:'Jira tickets',kind:'external'}];
window.fetch=async(url,options={})=>{
 const u=new URL(url,location.href);let data;
 if(u.pathname==='/api/scope-links'){
  if(options.method==='PUT'){
   const body=JSON.parse(options.body);
   assert(body.path==='/trees/topic'&&body.expected==='revision','exact checkout and revision preserved');
   if(failSave)return {ok:false,json:async()=>({detail:'Scope links changed elsewhere. Reopen the editor before saving.'})};
   saved=body;
  }
  data={links,types,revision:'revision'};
 }else if(u.pathname==='/api/assistant')data={configured:true,root:'/assistant',documents:[{id:'one',title:'Telesign Incident Room',path:'/notes/one.md'}]};
 else if(u.pathname==='/api/assistant/note')data={tree:{children:[{id:'rollout',title:'SDUI changes'}]}};
 else throw Error('Unexpected API '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
'''
    checks=r'''
(async()=>{
 const open=async()=>{await LabScopeLinks.edit('/trees/topic',()=>true,{kind:'worktree',label:'sdui/telesign-track3-unparseable-phone-error'});await until(()=>q('[data-link-card="doc"]')&&!q('[data-link-card="doc"]')._targetLoading)};
 const row=id=>q(`[data-link-card="${id}"]`);
 const input=(node,name,value)=>{const el=node.querySelector(`[data-${name}]`);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));return el};
 const fits=()=>{const d=document.querySelector('.scope-links-dialog'),r=d.getBoundingClientRect();assert(r.left>=0&&r.right<=innerWidth+1&&d.scrollWidth<=d.clientWidth+1,'editor fits viewport');for(const row of d.querySelectorAll('.scope-link-row-head')){assert(row.getBoundingClientRect().height<=48&&row.scrollWidth<=row.clientWidth+1,'every saved link is one line')}};
 await open();fits();
 assert(!q('select')&&[...q('[data-link-cards]').children].every(row=>row.querySelector('[data-link-fields]').hidden),'all saved rows compact and no manual type picker');
 for(const [id,service] of [['google','google-docs'],['discussion','confluence'],['slack','slack'],['jira','jira'],['github','github'],['grafana','grafana']])assert(row(id).querySelector('[data-link-service]')?.dataset.linkService===service,'correct actual service icon for '+id);
 assert(row('doc').querySelector('[data-row-label]').textContent==='Telesign Incident Room / SDUI changes','internal document and nested tab remain visible');
 for(const service of LAB_LINK_SERVICES){
  const img=new Image();img.src='/static/img/link-icons/'+service.icon;await img.decode();assert(img.naturalWidth>0,'bundled icon loads: '+service.id);
 }
 // The same compact icon wrapper retains its geometry and themed mono colors.
 for(const light of [true,false]){
  document.documentElement.style.setProperty('--text-primary',light?'#1f2328':'#e6edf3');
  document.documentElement.style.setProperty('--bg-primary',light?'#ffffff':'#0d1117');
  document.documentElement.style.setProperty('--bg-secondary',light?'#f6f8fa':'#161b22');
  document.documentElement.style.setProperty('--border',light?'#d0d7de':'#30363d');
  for(const id of ['google','slack','github','grafana']){const icon=row(id).querySelector('.scope-link-icon'),r=icon.getBoundingClientRect();assert(r.width===16&&r.height===16,'fixed icon size');if(id==='github')assert(getComputedStyle(icon).backgroundColor===getComputedStyle(icon).color,'GitHub icon inherits theme color');}
  fits();
 }
 row('slack').querySelector('[data-edit-link]').click();
 assert(!row('slack').querySelector('[data-link-fields]').hidden,'row click expands fields');
 input(row('slack'),'url','https://docs.google.com/spreadsheets/d/example/edit');
 input(row('slack'),'label','Incident tracker');
 assert(row('slack').querySelector('[data-link-service]').dataset.linkService==='google-sheets','changing URL updates icon immediately');
 row('slack').querySelector('[data-done-link]').click();assert(row('slack').querySelector('[data-link-fields]').hidden,'Done returns to one line');
 q('[data-add-link]').click();const added=q('[data-link-cards]').lastElementChild;
 assert(!added.querySelector('[data-link-fields]').hidden&&document.activeElement===added.querySelector('[data-url]'),'new link focuses URL');
 input(added,'url','javascript:alert(1)');q('form').requestSubmit();await until(()=>q('[data-message]').textContent.startsWith('Complete'));
 assert(!saved&&!added.querySelector('[data-link-fields]').hidden,'invalid URL cannot save and reveals its input');
 input(added,'url','https://example.test/reference');input(added,'label','Reference');added.querySelector('[data-done-link]').click();
 failSave=true;q('form').requestSubmit();await until(()=>q('[data-message]').textContent.includes('changed elsewhere'));
 assert(q('[data-link-card="slack"] [data-label]').value==='Incident tracker','stale save retains edits');
 failSave=false;q('form').requestSubmit();await until(()=>!document.querySelector('.scope-links-dialog'));
 assert(saved.links[0].id==='doc'&&saved.links[0].document_id==='one'&&saved.links[0].tab_id==='rollout','saving external edits preserves exact internal target');
 assert(saved.links[3].kind==='external'&&saved.links[3].url.includes('/spreadsheets/')&&saved.links[3].label==='Incident tracker','changed URL requests automatic inference');
 assert(saved.links[4].type==='jira'&&!saved.links[4].kind,'untouched custom-hosted type preserved');
 assert(saved.links.at(-1).kind==='external'&&saved.links.at(-1).url==='https://example.test/reference','unknown sites save as generic URLs');
 await open();row('grafana').querySelector('[data-remove]').click();assert(!row('grafana'),'remove action only removes its row');q('[data-close]').click();assert(confirms===1,'unsaved removal is protected');
 await open();q('[data-add-document]').click();await until(()=>q('[data-link-cards]').lastElementChild.querySelector('[data-document="one"]'));
 const internal=q('[data-link-cards]').lastElementChild;internal.querySelector('[data-document="one"]').click();await until(()=>internal.querySelector('[data-tab="rollout"]'));
 internal.querySelector('[data-tab="rollout"]').click();internal.querySelector('[data-finish-document]').click();internal.querySelector('[data-done-link]').click();
 assert(internal.querySelector('[data-link-fields]').hidden&&internal.querySelector('[data-row-label]').textContent.includes('SDUI changes'),'new internal link keeps document/tab picker and compact summary');
 q('[data-close]').click();await open();fits();
 if(innerWidth<600){document.documentElement.style.setProperty('--text-primary','#1f2328');document.documentElement.style.setProperty('--text-secondary','#59636e');document.documentElement.style.setProperty('--bg-primary','#ffffff');document.documentElement.style.setProperty('--bg-secondary','#f6f8fa');document.documentElement.style.setProperty('--border','#d0d7de');}
 document.getElementById('result').textContent='PASS compact rows, branded icons, automatic inference, edits, validation, revision recovery, exact document targets, responsive themes';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    (tmp_path/'static').symlink_to(static,target_is_directory=True)
    page=tmp_path/'link-editor.html'
    page.write_text('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#8b949e;--text-dim:#6e7681;--border:#30363d;--accent:#58a6ff}body{background:var(--bg-primary);font-family:system-ui}.scope-links-heading h2{overflow-wrap:anywhere}</style><pre id="result">PENDING</pre><script>window.LAB_LINK_SERVICES='+json.dumps(registry)+';'+setup+'</script><script src="/static/js/lib/scope-links.js"></script><script>'+checks+'</script>')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(tmp_path)))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),f'http://127.0.0.1:{server.server_port}/{page.name}',str(tmp_path/'dom.html'),str(tmp_path/'link-editor.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
        server.shutdown();server.server_close();thread.join(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
