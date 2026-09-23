"""Central settings in real Chrome, with actual scoped storage helpers and fake APIs."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'core/src/core/static'


@pytest.mark.parametrize('viewport', [1440, 390])
def test_settings_center_browser(tmp_path, viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:pytest.skip('Chrome and Node required')
    app=(STATIC/'js/lab-app.js').read_text()
    def between(start,end):
        at=app.index(start)
        return app[at:app.index(end,at)]
    helpers='\n'.join([
        between('let showDotFiles = false;','function filterDotFiles(nodes)'),
        between('const _TERM_NEW_OPTIONS =','function _termRenderNewOptionsSettings()'),
        between('function _termSessionsKey(','// Home owns one terminal pool.'),
        between('window.LabSettingsBridge = {','async function openSettings()'),
    ])
    # Exercise the actual first statements in existing entry points, without
    # dragging in their retired fallback modal renderers.
    for name in ['openSettings','termOpenSettings','openSidebarFileConfig']:
        at=app.index('function '+name+'(')
        line=app[app.index('\n',at)+1:].splitlines()[0]
        assert 'window.LabSettings' in line
        helpers+='\nfunction '+name+'(){'+line+'}\n'
    setup=r'''
localStorage.clear();
const currentWorkspace={name:'same',path:'/vault-a/same',vault:'a',display_name:'Workspace Alpha'};
const currentRepo=null, SELF_WORKSPACE_ID='__self__',SELF_REPO_PATH='/lab',ASSISTANT_WORKSPACE_ID='__assistant__',ASSISTANT_VAULT_ID='__assistant__',ASSISTANT_ROOT='/assistant';
let _settings={},_vaultAgentPolicy=null,termSessionOrientation='vertical',termRecentMinutes=60,termRecentColor='#3fb950',rendered=0,appliedOptions=0;
const _termActiveWorkspaceId=()=>currentWorkspace.name,_termVaultId=()=>currentWorkspace.vault,_termGroupScopeKey=()=>_termSessionsKey(currentWorkspace.name,currentWorkspace.vault);
const applyTheme=()=>{},termRenderSessionList=()=>++rendered,_termApplyNewOptions=()=>++appliedOptions;
const termSetSessionView=(_,v)=>termSessionOrientation=v,termSetRecentMinutes=v=>termRecentMinutes=v,termSetRecentColor=v=>termRecentColor=v;
const termKillAll=()=>{throw Error('must never stop sessions')};
const esc=v=>String(v),escAttr=esc;
window.LAB_IS_ADMIN=true;
let discard=true;window.confirm=()=>discard;
const assert=(v,m)=>{if(!v)throw Error(m)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
const cfg={defaultAgent:'claude',model:null,theme:'dark',autopilot:{claude:true,codex:false,copilot:false},documentTerminals:{enabled:true,sleepMinutes:60,expireHours:36,maxRunning:3}};
const available={claude:false,codex:true,copilot:true},calls=[];
const overrides={a:{agent:null,model:null},b:{agent:'copilot',model:'saved-model'}};
let failSave=false,delayA=false,releaseA;
window.fetch=async(url,opts={})=>{
 const u=new URL(url,'https://lab.test'),body=opts.body?JSON.parse(opts.body):undefined;
 calls.push({path:u.pathname,vault:u.searchParams.get('vault'),body});
 let data;
 if(u.pathname==='/api/settings/global'){
  if(body){if(failSave)return {ok:false,json:async()=>({detail:'Save failed; retry'})};Object.assign(cfg,body)}data=cfg;
 }else if(u.pathname==='/api/settings')data=cfg;
 else if(u.pathname==='/api/agents/available')data=available;
 else if(u.pathname==='/api/vaults/workspaces')data={vaults:[
  {id:'a',name:'Vault A',workspace_rows:[{name:'same',display_name:'Workspace Alpha',path:'/vault-a/same',is_workspace:true}]},
  {id:'b',name:'Vault B',workspace_rows:[{name:'same',display_name:'Workspace Beta',path:'/vault-b/same',is_workspace:true}]},
  {id:'offline',name:'Offline',unavailable:true}]};
 else if(u.pathname==='/api/vault/agents')data={supported:['claude','codex','copilot'],default:cfg.defaultAgent};
 else if(u.pathname==='/api/workspaces/same'){if(delayA&&u.searchParams.get('vault')==='a')await new Promise(r=>releaseA=r);data=overrides[u.searchParams.get('vault')]}
 else if(u.pathname==='/api/workspaces/same/agent'){Object.assign(overrides[u.searchParams.get('vault')],body);data={ok:true}}
 else if(u.pathname==='/api/sidebar-worktrees')data={folders:[{path:'/trees/feature'}]};
 else throw Error('Unexpected API '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
'''
    checks=r'''
_refreshSidebarAfterFileConfig=()=>++rendered;
const q=selector=>document.querySelector('#labSettingsCenter '+selector);
const form=()=>q('form');
const field=(name,value)=>{const el=form().elements[name];if(el.type==='checkbox')el.checked=value;else el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}));};
const save=async()=>{form().requestSubmit();await until(()=>q('[data-message]').textContent==='Saved')};
const scope=async path=>{q(`[data-scope="${path}"]`).click();await until(()=>form()?.elements.agent)};
const section=async name=>{q(`[data-section="${name}"]`).click();await until(()=>form())};
const fits=()=>{const d=document.getElementById('labSettingsCenter');const rect=d.getBoundingClientRect();assert(rect.right<=innerWidth+1,'dialog fits');assert(Math.abs(rect.left-(innerWidth-rect.width)/2)<=1,'dialog stays centered with Lab CSS');for(const el of d.querySelectorAll('main,aside'))assert(el.scrollWidth<=el.clientWidth+1,'no horizontal overflow in '+el.tagName)};
(async()=>{
 _sidebarFileConfigScope=encodeURIComponent(currentWorkspace.path);
 _sidebarFileConfig=_sidebarNormalizeFileConfig({showHidden:false,filesSort:'updated',folderScopes:[{path:'/alpha/files',label:'A',color:'#00ff00'}]});
 LabSettingsBridge.saveSidebar(LabSettingsBridge.currentScope('files'),_sidebarFileConfig);
 rendered=0;
 const aKey='labSidebarFileConfig-v2:'+encodeURIComponent(currentWorkspace.path),beforeA=localStorage.getItem(aKey);
 localStorage.setItem('labTermNewOptions-v1:a::same','["codex","terminal"]');
 const focus=document.getElementById('terminalInput');focus.focus();
 focus.dispatchEvent(new KeyboardEvent('keydown',{key:',',code:'Comma',metaKey:true,bubbles:true,cancelable:true}));
 await until(()=>form()?.elements.defaultAgent&&q('[data-scope="/vault-b/same"]'));
 assert(document.querySelectorAll('#labSettingsCenter').length===1,'one settings dialog');
 assert(form().elements.defaultAgent.querySelector('[value="claude"]').disabled,'uninstalled Claude labelled and disabled');
 assert(q('[data-catalog-status]').textContent.includes('1 vault is'),'offline vault visible');fits();
 assert(q('[name="auto_codex"]').getAttribute('role')==='switch','boolean settings are accessible switches');
 q('[data-search]').value='font';q('[data-search]').dispatchEvent(new Event('input'));
 assert(q('[data-section="appearance"]')&&!q('[data-section="documents"]'),'search finds font settings');
 q('[data-section="appearance"]').click();await until(()=>q('[name="documentFontSize"]'));
 assert(q('[name="documentFontSize"]').value==='18','larger document default');fits();
 const samples=document.createElement('div');samples.innerHTML=`<div class="nb-markdown" id="outsideModal">Outside</div><div class="doc-modal-body"><div class="workspace-content"><div class="nb-markdown" id="fileText"><h2>Heading</h2><p>Paragraph</p><code>Code</code></div><textarea id="workspaceDocEditor" style="font-size:15px">Editor</textarea></div><div class="nb-cell-edit-wrap"><pre class="nb-cell-edit-highlight">Code</pre><textarea class="nb-cell-edit-area">Code</textarea></div></div><div class="assistant-document-modal"><div class="assistant-document-pane"><div class="assistant-markdown" id="noteText">Note<table><tr><td>Cell</td></tr></table></div><div class="assistant-note-editor"><pre class="assistant-note-marks"><span>Line</span><span></span></pre><textarea>Line\n</textarea></div></div><div class="xterm-screen" style="font:13px monospace"><canvas></canvas></div></div>`;
 document.body.append(samples);
 const size=selector=>getComputedStyle(samples.querySelector(selector)).fontSize;
 const outsideSize=size('#outsideModal'),terminalSize=size('.xterm-screen');
 const resizeFont=(name,value)=>{const el=q(`[name="${name}"]`);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));};
 resizeFont('documentFontSize',24);resizeFont('modalFontSize',20);fits();
 assert(size('#fileText')==='24px'&&size('#fileText p')==='24px'&&size('#noteText')==='24px'&&size('#noteText table')==='24px','reading text and tables resize together');
 assert(size('#fileText h2')==='37.2px'&&parseFloat(size('#fileText code'))>20,'headings and inline code scale');
 assert(size('#workspaceDocEditor')==='24px'&&size('.assistant-note-editor textarea')==='24px'&&size('.assistant-note-marks')==='24px','document editors scale with reading text');
 assert(size('.nb-cell-edit-highlight')===size('.nb-cell-edit-area'),'notebook editor overlay stays aligned');
 assert(size('#outsideModal')===outsideSize&&size('.xterm-screen')===terminalSize,'outside reading surfaces and terminal canvas remain unchanged');
 assert(getComputedStyle(q('.settings-preview-document')).fontSize==='24px'&&getComputedStyle(q('[data-title]')).fontSize!=='21px','live preview and settings UI resize');
 assert(JSON.parse(localStorage.getItem('labModalTypography-v1')).documentFontSize===24,'font preferences persisted');
 const reloadFrame=document.createElement('iframe');reloadFrame.hidden=true;document.body.append(reloadFrame);
 const settingsScript=document.createElement('script');settingsScript.textContent=document.querySelectorAll('script')[2].textContent;reloadFrame.contentDocument.head.append(settingsScript);
 assert(reloadFrame.contentDocument.documentElement.style.getPropertyValue('--lab-document-font-size')==='24px','saved size applied on fresh page initialization');reloadFrame.remove();
 LabSettings.close();await LabSettings.open({section:'appearance'});await until(()=>q('[name="documentFontSize"]'));
 assert(q('[name="documentFontSize"]').value==='24'&&q('[name="modalFontSize"]').value==='20','saved font sizes restored');
 resizeFont('documentFontSize',32);resizeFont('modalFontSize',24);fits();
 q('[data-reset="documentFontSize"]').click();q('[data-reset="modalFontSize"]').click();
 assert(size('#fileText')==='18px'&&q('[name="modalFontSize"]').value==='14','individual font resets');
 resizeFont('documentFontSize',12);
 const marks=samples.querySelector('.assistant-note-marks'),editor=samples.querySelector('.assistant-note-editor textarea');
 assert(getComputedStyle(marks).lineHeight===getComputedStyle(editor).lineHeight&&Math.abs(marks.children[1].getBoundingClientRect().height-19.8)<.1,'blank editor lines stay aligned at smallest size');
 q('[data-reset="documentFontSize"]').click();samples.remove();
 document.body.classList.add('light-mode');fits();document.body.classList.remove('light-mode');
 await section('general');
 field('theme','light');await save();
 assert(cfg.defaultAgent==='claude'&&calls.find(c=>c.body)?.body.theme==='light','theme does not change default agent');
 field('defaultAgent','codex');await save();assert(cfg.defaultAgent==='codex'&&cfg.model===null,'choose installed global agent');
 await scope('/vault-b/same');
 assert(form().elements.agent.value==='copilot'&&form().elements.model.value==='saved-model','load inactive workspace explicit vault');
 field('agent','');field('model','');await save();
 assert(overrides.b.agent===null&&overrides.a.agent===null&&q('[data-panel]').textContent.includes('Codex'),'clear override and refresh effective agent');
 assert(calls.filter(c=>c.path==='/api/workspaces/same/agent').every(c=>c.vault==='b'),'save correct vault for duplicate workspace ID');
 await section('terminals');field('claude',false);field('copilot',false);await save();
 assert(localStorage.getItem('labTermNewOptions-v1:a::same')==='["codex","terminal"]','active terminal options untouched');
 assert(localStorage.getItem('labTermNewOptions-v1:b::same')==='["codex","terminal","attach"]','inactive terminal options scoped');
 assert(q('[data-stop]').disabled&&!appliedOptions,'inactive workspace cannot stop active sessions');
 await section('files');fits();field('showHidden',true);field('filesSort','type');
 q('[data-add-folder]').click();const card=q('[data-folder-card="folder"]');card.querySelector('[data-path]').value='notes';card.querySelector('[data-label]').value='Notes';
 card.querySelector('[data-worktree]').value='/trees';card.querySelector('[data-scan]').click();await until(()=>card.querySelector('[data-scan-status]').textContent==='1 worktrees found');
 q('[data-worktree-color]').value='#123456';await save();
 const bKey='labSidebarFileConfig-v2:'+encodeURIComponent('/vault-b/same'),b=JSON.parse(localStorage.getItem(bKey));
 assert(b.showHidden&&b.filesSort==='type'&&b.folderScopes[0].path==='/vault-b/same/notes'&&b.worktreeColors['/trees/feature']==='#123456','inactive files prefs and worktree colors saved');
 assert(localStorage.getItem(aKey)===beforeA&&!_sidebarFileConfig.showHidden&&!rendered,'inactive save never mutates active sidebar');
 field('recentMinutes','60');discard=false;q('[data-scope="global"]').click();
 assert(form().elements.recentMinutes.value==='60'&&q('[data-title]').textContent.includes('Beta'),'dirty navigation can be cancelled');
 discard=true;q('[data-scope="global"]').click();await until(()=>form()?.elements.defaultAgent);
 await section('documents');field('sleepMinutes','20');field('maxRunning','2');await save();assert(cfg.documentTerminals.sleepMinutes===20&&cfg.documentTerminals.maxRunning===2,'global policy saved');
 await section('terminals');assert(form().elements.completionReadSeconds.value==='20','completion delay defaults to twenty seconds');
 field('orientation','horizontal');field('completionReadSeconds','7');await save();assert(termSessionOrientation==='horizontal','appearance bridge');
 assert(localStorage.getItem('labTerminalCompletionReadSeconds')==='7','completion delay persisted');
 await section('documents');await section('terminals');assert(form().elements.completionReadSeconds.value==='7','saved delay restored');
 await section('general');field('theme','dark');failSave=true;form().requestSubmit();await until(()=>q('[data-message]').classList.contains('error'));
 assert(form().elements.theme.value==='dark'&&document.getElementById('labSettingsCenter').open,'failed save keeps draft');failSave=false;await save();
 delayA=true;q('[data-scope="/vault-a/same"]').click();await until(()=>releaseA);
 await scope('/vault-b/same');releaseA();await new Promise(r=>setTimeout(r,15));assert(q('[data-title]').textContent.includes('Beta'),'late response cannot overwrite new scope');delayA=false;
 LabSettings.close();assert(document.activeElement===focus,'close restores focus');
 await termOpenSettings();await until(()=>form()?.elements.attach);assert(q('[data-title]').textContent==='Workspace Alpha · Terminal sessions','local terminal settings shortcut');LabSettings.close();
 await openSidebarFileConfig();await until(()=>form()?.elements.showHidden);assert(q('[data-title]').textContent==='Workspace Alpha · File sidebar','local file sidebar shortcut');LabSettings.close();
 focus.dispatchEvent(new KeyboardEvent('keydown',{key:',',ctrlKey:true,bubbles:true,cancelable:true}));await until(()=>form()?.elements.defaultAgent);fits();
 assert(currentWorkspace.path==='/vault-a/same'&&!calls.some(c=>c.path.includes('/term/sessions')),'opening or saving settings never changes workspace or launches terminals');
 q('[data-section="appearance"]').click();await until(()=>q('[name="documentFontSize"]'));fits();
 document.getElementById('result').textContent='PASS scoped settings, typography, responsive switches, shortcuts, policy, drafts, late responses';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    page=tmp_path/'settings.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/settings-center.css').read_text()+'</style><body><input id="terminalInput"><pre id="result">PENDING</pre><script>'+setup+'\n'+helpers+'</script><script>'+(STATIC/'js/lib/terminal-completion.js').read_text()+'</script><script>'+(STATIC/'js/lib/settings-center.js').read_text()+'</script><script>'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs'
        driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'settings.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
    print(tmp_path/'settings.png',result[1])
