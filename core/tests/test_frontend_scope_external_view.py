"""Workspace links occupy only the center, sharing document navigation guards."""
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

from .test_assistant_document_tasks import owned_tasks, legacy_tasks  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


@pytest.mark.parametrize('viewport,collapsed', [(1440, False), (1440, True), (390, True)])
def test_external_link_center_panel_browser(client, owned_tasks, tmp_path, viewport, collapsed):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    root, note, *_ = owned_tasks
    path = note.relative_to(root).as_posix()
    details = {}

    def visit(row):
        details[row['path']] = client.get('/api/assistant/note', params={'path':row['path']}).json()
        for child in row['children']:
            visit(child)

    detail = client.get('/api/assistant/note', params={'path':path}).json()
    visit(detail['tree'])
    fixture = {'index':client.get('/api/assistant').json(), 'details':details, 'path':path,
               'link':{'assistant_root':str(root), 'document_id':note.stem, 'path':path,
                       'title':'Weekly product review'}, 'collapsed':collapsed}
    # A real cross-origin app proves the frame can load and retain its state.
    (tmp_path/'embedded.html').write_text('<!doctype html><title>Embedded tool</title><h1>Team dashboard</h1><input id="draft"><script>parent.postMessage({embedded:true}, "*");</script>')
    (tmp_path/'static').symlink_to(STATIC, target_is_directory=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture['url'] = f'http://localhost:{server.server_port}/embedded.html?org=1&theme=dark#dashboard'
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<400;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
let activeRoot='/trees/topic', pendingIndex, pendingDetail, releaseIndex, releaseDetail, loads=0, fileNavigation=0;
const calls=[], tabs=[];
window.LAB_EXTERNAL_BROWSER=true;
window.LabTaskTerminalBridge={cancelNavigation:()=>fileNavigation++};
window.open=(...args)=>tabs.push(args);
window.addEventListener('message',event=>{if(event.origin===new URL(FIX.url).origin&&event.data?.embedded)loads++});
const external={id:'google',kind:'external',url:FIX.url,label:'Team dashboard',type:'grafana'};
window.fetch=async(url,options={})=>{
 const u=new URL(url,location.href),body=options.body?JSON.parse(options.body):null;
 calls.push({path:u.pathname,method:options.method||'GET',body});let data;
 if(u.pathname==='/api/scope-links')data={links:[{...FIX.link,id:'doc',kind:'internal'},external],types:[],revision:'v1'};
 else if(u.pathname==='/api/assistant'){if(pendingIndex)await pendingIndex;data=FIX.index}
 else if(u.pathname==='/api/assistant/note'){if(pendingDetail)await pendingDetail;data=FIX.details[u.searchParams.get('path')]}
 else if(u.pathname==='/api/assistant/content')return {ok:false,json:async()=>({detail:'Offline — keep the draft'})};
 else throw Error('Unexpected request '+url);
 return {ok:!!data,json:async()=>structuredClone(data)};
};
window.Terminal=class{constructor(){throw Error('External link must not create a terminal')}};
window.WebSocket=class{constructor(){throw Error('External link must not reconnect a terminal')}};
'''
    checks = r'''
(async()=>{
 const links=document.querySelector('[data-scope-links]');
 await LabScopeLinks.mount(links,()=>activeRoot==='/trees/topic');
 const button=()=>links.querySelector('[data-scope-link="1"]');
 const host=()=>document.querySelector('.workspace-external-host');
 const frame=()=>host()?.querySelector('iframe');
 const localDraft=document.getElementById('localDraft'),terminal=document.getElementById('termPanel'),terminalDraft=document.getElementById('terminalDraft');
 localDraft.value='Unsent file changes';terminalDraft.value='Unsent terminal command';
 const guard=AssistantView.navigationGuard();button().focus();button().click();
 assert(!guard(),'external selection cancels older scope/document navigation');
 assert(fileNavigation===1,'external selection cancels pending linked-file navigation');
 await until(()=>loads===1);
 assert(frame().src===FIX.url,'query, hash and original URL preserved');
 assert(!tabs.length&&!calls.some(c=>c.path==='/api/ui/open-external'),'ordinary click stays in the middle panel');
 assert(button().getAttribute('aria-current')==='page','selected chip highlighted');
 assert(frame().title==='Team dashboard'&&host().getAttribute('aria-label')==='Team dashboard','accessible embedded content');
 assert(host().querySelector('[data-link-service]').dataset.linkService==='grafana','toolbar uses the same service icon');
 const r=host().getBoundingClientRect(),side=document.getElementById('sidebar').getBoundingClientRect(),term=terminal.getBoundingClientRect();
 if(innerWidth>760){assert(Math.abs(r.right-term.left)<2&&Math.abs(r.top-term.top)<2,'center aligns beside the existing terminal');assert(r.left===(FIX.collapsed?0:side.right),'Files never absorbed into the external view');assert(document.elementFromPoint(term.left+100,term.top+100).closest('#termPanel')===terminal,'terminal remains interactive');}
 assert(r.right<=innerWidth+1&&r.bottom<=innerHeight+1&&r.width>0,'view fits available viewport');
 assert(host().scrollWidth<=host().clientWidth+1,'toolbar fits center on mobile');
 if(innerWidth>760){
  document.body.style.setProperty('--term-width',FIX.collapsed?'1080px':'800px');
  assert(host().clientWidth>=300&&host().scrollWidth<=host().clientWidth+1,'toolbar fits a narrow middle panel without covering Files or terminal');
  document.body.style.setProperty('--term-width','400px');
 }
 assert(document.body.classList.contains('sidebar-collapsed')===FIX.collapsed,'saved Files choice preserved');
 assert(document.getElementById('localDraft')===localDraft&&localDraft.value==='Unsent file changes'&&terminalDraft.value==='Unsent terminal command','existing editor and terminal drafts retained');
 let first=frame();button().click();await LabScopeLinks.mount(links,()=>activeRoot==='/trees/topic');
 await new Promise(r=>setTimeout(r,20));assert(frame()===first&&loads===1,'repeated activation and metadata refresh retain the live frame');
 host().querySelector('[data-browser]').click();
 assert(tabs.length===1&&tabs[0][0]===FIX.url&&tabs[0][2].includes('noopener')&&!calls.some(c=>c.path==='/api/ui/open-external'),'browser button opens on clicking client even over SSH');
 host().querySelector('[data-reload]').click();await until(()=>loads===2);assert(frame().src===FIX.url,'explicit reload retains original URL including hash');first=frame();
 button().dispatchEvent(new MouseEvent('click',{bubbles:true,metaKey:true,button:0}));assert(tabs.length===2&&frame()===first,'modified click opens browser without replacing center');
 assert(LabScopeLinks.openExternal({url:'javascript:alert(1)'},activeRoot)===false&&LabScopeLinks.openExternal({url:'data:text/html,hello'},activeRoot)===false,'reject executable or nonweb URLs');
 assert(LabScopeLinks.openExternal({...external,url:FIX.url+'other'},activeRoot,{isCurrent:()=>false})===false&&frame()===first,'inactive checkout cannot open a link');
 host().querySelector('[data-close]').click();
 assert(!host()&&getComputedStyle(document.getElementById('content')).display!=='none','close restores original content');
 if(!FIX.collapsed)assert(document.activeElement===button(),'close restores keyboard focus to visible link');
 assert(!button().hasAttribute('aria-current')&&terminalDraft.value==='Unsent terminal command','close clears selection and preserves terminal');
 // Pending internal document reads must never displace a newer external click.
 for(const stage of ['index','detail']){
  const endpoint=stage==='index'?'/api/assistant':'/api/assistant/note';
  const before=calls.filter(c=>c.path===endpoint).length;
  if(stage==='index')pendingIndex=new Promise(r=>releaseIndex=r);else pendingDetail=new Promise(r=>releaseDetail=r);
  const pending=AssistantView.openLinkedTask(FIX.link,{wholeDocument:true});
  await until(()=>calls.filter(c=>c.path===endpoint).length>before);
  button().click();const latest=frame();
  if(stage==='index')releaseIndex();else releaseDetail();
  await pending;pendingIndex=null;pendingDetail=null;
  assert(frame()===latest&&!document.querySelector('#assistantDocumentModal.active'),'new external click wins during '+stage+' read');
 }
 pendingIndex=new Promise(r=>releaseIndex=r);
 const closing=AssistantView.openLinkedTask(FIX.link,{wholeDocument:true});
 host().querySelector('[data-close]').click();releaseIndex();await closing;pendingIndex=null;
 assert(!host()&&!document.querySelector('#assistantDocumentModal.active'),'closing link also cancels a document still loading');
 // Switching between document and link uses the real document lifecycle.
 await AssistantView.openLinkedTask(FIX.link,{wholeDocument:true,inline:true});
 assert(!host()&&document.body.classList.contains('assistant-inline-document'),'internal document replaces link');
 document.getElementById('assistantEditNote').click();await until(()=>document.querySelector('.assistant-note-editor textarea'));
 const draft=document.querySelector('.assistant-note-editor textarea');
 draft.value='Keep offline document draft';draft.dispatchEvent(new Event('input',{bubbles:true}));
 button().click();assert(host()&&!document.querySelector('#assistantDocumentModal.active'),'link replaces document in center');
 await until(()=>calls.some(c=>c.path==='/api/assistant/content'));
 await AssistantView.openLinkedTask(FIX.link,{wholeDocument:true,inline:true});
 assert(document.querySelector('.assistant-note-editor textarea').value==='Keep offline document draft','failed draft save survives link navigation');
 button().click();AssistantView.closeInlineDocument();assert(!host(),'file/dashboard navigation clears external view');
 button().click();AssistantView.closeDocument(false);assert(!host(),'workspace navigation clears external view');
 // A second external link replaces the old frame, including across roots.
 button().click();const old=frame();
 LabScopeLinks.openExternal({...external,url:FIX.url+'new',label:'Another dashboard'},'/trees/other');
 assert(!old.isConnected&&frame()!==old&&host().getAttribute('aria-label')==='Another dashboard','next link replaces old frame and title');
 LabScopeLinks.closeExternal();
 // Known framing blockers open on the client without disrupting the center.
 button().click();const currentFrame=frame(),beforeTabs=tabs.length;
 for(const url of ['https://grid-example.enterprise.slack.com/archives/C1', 'https://github.com/org/repo',
   'https://teams.microsoft.com/v2/', 'https://bitbucket.org/team/repo', 'https://linear.app/team/issue/1',
   'https://www.notion.so/page', 'https://www.figma.com/design/123']){
  await LabScopeLinks.openExternal({...external,url},activeRoot);
  assert(tabs.at(-1)[0]===url&&frame()===currentFrame,'framing blocker opens browser and preserves current document: '+url);
 }
 assert(tabs.length===beforeTabs+7,'each known blocker opens exactly once');
 LabScopeLinks.closeExternal();
 for(const url of ['https://slack.com.example.test/path', 'https://embed.figma.com/design/123?embed-host=lab', 'https://www.figma.com/embed?url=test']){
  LabScopeLinks.openExternal({...external,url},activeRoot);
  assert(frame()?.src===url&&tabs.length===beforeTabs+7,'lookalike domains and supported Figma embeds retain middle panel: '+url);
  LabScopeLinks.closeExternal();
 }
 // The icon/type does not determine framing: self-hosted tools remain embeddable.
 LabScopeLinks.openExternal({...external,type:'slack'},activeRoot);
 assert(frame()?.src===FIX.url&&tabs.length===beforeTabs+7,'self-hosted Slack icon does not force browser opening');
 // Remember a failure for this origin, including its port, and restore the editor.
 host().querySelector('[data-remember-browser]').click();
 const preferenceKey='lab.scope-links.browser-origins.v1';
 assert(!host()&&tabs.at(-1)[0]===FIX.url&&JSON.parse(localStorage.getItem(preferenceKey)).includes(new URL(FIX.url).origin),'remember browser saves origin and closes embedded view');
 assert(button().title.startsWith('Opens in browser'),'remembered destination is visible on the chip');
 const count=tabs.length;button().click();
 assert(tabs.length===count+1&&!host(),'future activation skips refused embedded view');
 LabScopeLinks.openExternal({...external,url:FIX.url.replace('localhost','127.0.0.1')},activeRoot);
 assert(frame(),'browser preference is scoped to an origin');LabScopeLinks.closeExternal();
 // A fresh module/page session reads the saved preference.
 await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/static/js/lib/scope-links.js';script.onload=resolve;script.onerror=reject;document.head.append(script)});
 await LabScopeLinks.mount(links,()=>activeRoot==='/trees/topic');
 const restored=tabs.length;button().click();
 assert(tabs.length===restored+1&&!host(),'saved browser preference survives a new page session');
 await LabScopeLinks.edit(activeRoot,()=>true);
 const editor=document.querySelector('.scope-links-dialog'),card=editor.querySelector('[data-link-card="google"]');
 card.querySelector('[data-edit-link]').click();
 assert(!card.querySelector('[data-browser-preference]').hidden&&!card.querySelector('[data-reset-browser]').hidden,'editor exposes browser preference and its reset');
 card.querySelector('[data-reset-browser]').click();
 assert(card.querySelector('[data-browser-preference]').hidden&&!JSON.parse(localStorage.getItem(preferenceKey)).length,'reset returns site to middle panel');
 window.confirm=()=>{throw Error('Browser preference must not mark metadata dirty')};
 editor.querySelector('[data-close]').click();
 assert(!document.querySelector('.scope-links-dialog')&&!calls.some(c=>c.path==='/api/scope-links'&&c.method==='PUT'),'reset needs no metadata save');
 // Leave the real view mounted for screenshot review.
 button().click();await until(()=>loads>=3);
 document.getElementById('result').textContent='PASS center layout, live embed, reload, drafts, client browser, selection and navigation cancellation';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js', 'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js', 'js/views/assistant.js', 'js/views/assistant-tasks.js',
        'js/lib/external-links.js', 'js/lib/scope-links.js'])
    page = tmp_path/'external-view.html'
    classes = 'workspace-active has-repo-tabs term-open' + (' sidebar-collapsed' if collapsed else '') + (' term-collapsed' if viewport < 760 else '')
    page.write_text('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css"><style>'+(STATIC/'css/assistant-tasks.css').read_text()+(STATIC/'css/workspace-documents.css').read_text()+'</style>'
        '<body class="'+classes+'" style="--sidebar-width:300px;--term-width:400px"><div class="topbar">Lab</div><div id="repoTabs"></div><div class="layout"><aside id="sidebar" class="sidebar"><section class="sidebar-scope-links" data-scope-links="/trees/topic"></section></aside><main id="content" class="main"><textarea id="localDraft"></textarea></main></div><aside id="termPanel" class="term-panel"><h3>Existing workspace terminal</h3><textarea id="terminalDraft"></textarea></aside><pre id="result" style="position:fixed;bottom:0;left:0;z-index:1000;font-size:8px">PENDING</pre>'
        '<script>const FIX='+json.dumps(fixture).replace('</',r'<\/')+';window.LAB_LINK_SERVICES='+(STATIC/'link-services.json').read_text()+';</script><script>'+setup+'</script>'+scripts+'<script>'+checks+'</script>')
    profile = tmp_path/'profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--user-data-dir='+str(profile), '--remote-debugging-port=0', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        driver = tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result = subprocess.run([node, str(driver), str(profile), f'http://127.0.0.1:{server.server_port}/{page.name}', str(tmp_path/'dom.html'), str(tmp_path/'external-view.png')], capture_output=True, text=True, timeout=30, env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    result = re.search(r'<pre id="result"[^>]*>(.*?)</pre>', html, re.S)
    assert result and result[1].startswith('PASS'), result[1] if result else html[-2000:]
