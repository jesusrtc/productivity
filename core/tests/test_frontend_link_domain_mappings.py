"""Real upload, settings persistence, and live icon updates in desktop/mobile Chrome."""
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

ROOT=Path(__file__).resolve().parents[2]
STATIC=ROOT/'core/src/core/static'


@pytest.mark.parametrize('viewport',[1440,390])
def test_domain_icon_settings_and_uploaded_icons_in_browser(tmp_path,viewport):
    chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node=shutil.which('node')
    if not Path(chrome).is_file() or not node:pytest.skip('Chrome and Node required')
    registry=json.loads((STATIC/'link-services.json').read_text())
    checks=r'''
localStorage.clear();
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out: '+fn)};
const cfg={theme:'dark',scopeLinkTypes:[{id:'internal-docs',name:'Internal docs',kind:'internal'},{id:'google-docs',name:'Google Docs',kind:'external'}],linkDomainMappings:[]};
const links=[{id:'grafana',kind:'external',type:'url',label:'Production metrics',url:'https://mygrafana.mycompany.com/d/traffic'},
 {id:'custom',kind:'external',type:'url',label:'Operations console',url:'https://console.mycompany.com/page'}];
const requests=[];let failSave=false,releaseOld;
window.confirm=()=>true;
window.LabSettingsBridge={initialScopes:()=>[],settingsSaved(){}};
window.fetch=async(url,options={})=>{
 const u=new URL(url,location.href);let data;
 if(u.pathname==='/api/settings/global'){
  if(options.body){const body=JSON.parse(options.body);requests.push(body);if(failSave)return {ok:false,json:async()=>({detail:'Save failed; retry'})};Object.assign(cfg,body);cfg.linkDomainMappings=cfg.linkDomainMappings.map(row=>({...row,domain:row.domain.toLowerCase().replace(/\.$/, '')}));}data=cfg;
 }else if(u.pathname==='/api/agents/available')data={claude:true,codex:true,copilot:true};
 else if(u.pathname==='/api/vaults/workspaces')data={vaults:[]};
 else if(u.pathname==='/api/scope-links'){
  data={links,types:cfg.scopeLinkTypes,linkDomainMappings:structuredClone(cfg.linkDomainMappings),revision:'revision'};
  if(u.searchParams.get('path')==='/late')await new Promise(resolve=>releaseOld=resolve);
 }else throw Error('Unexpected API '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
const q=s=>document.querySelector('#labSettingsCenter '+s);
const rows=()=>[...(q('[data-domain-mappings]')?.children||[])];
const change=(card,key,value)=>{const input=card.querySelector(`[data-${key}]`);if(input.type==='checkbox')input.checked=value;else input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}));};
const save=async()=>{q('form').requestSubmit();await until(()=>q('[data-message]').textContent==='Saved')};
const upload=async(card,name,contents,type)=>{
 const input=card.querySelector('[data-upload-icon]'),transfer=new DataTransfer();transfer.items.add(new File([contents],name,{type}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));await until(()=>!card._uploading);
};
const fits=()=>{const d=document.getElementById('labSettingsCenter'),r=d.getBoundingClientRect();assert(r.left>=0&&r.right<=innerWidth+1,'settings fits viewport');for(const el of d.querySelectorAll('main,.settings-domain-mapping'))assert(el.scrollWidth<=el.clientWidth+1,'mapping fields fit available width')};
(async()=>{
 const sidebar=document.getElementById('links');await LabScopeLinks.mount(sidebar,()=>true);
 assert(!sidebar.querySelector('[data-link-service]'),'unknown company hostname starts with generic icon');
 // A read started before a settings save cannot replace the newer configuration.
 const late=document.createElement('section');late.dataset.scopeLinks='/late';document.body.append(late);const pending=LabScopeLinks.mount(late,()=>true);await until(()=>releaseOld);
 await LabSettings.open({section:'links'});await until(()=>q('[data-add-domain]'));
 assert(q('[data-title]').textContent==='Global · Links and icons','discoverable settings section');
 q('[data-add-domain]').click();const grafana=rows()[0];
 assert([...grafana.querySelector('[data-domain-service]').options].some(option=>option.value==='grafana'),'Grafana is in icon list');
 change(grafana,'domain','MYGRAFANA.MyCompany.com.');change(grafana,'domain-service','grafana');change(grafana,'tool-name','My Grafana');fits();
 assert(grafana.querySelector('[data-icon-preview] [data-link-service="grafana"]'),'built-in icon previews immediately');
 await save();releaseOld();await pending;
 assert(grafana.querySelector('[data-domain]').value==='mygrafana.mycompany.com','saved domain normalization appears in form');
 assert(sidebar.querySelector('[data-scope-link="0"] [data-link-service="grafana"]'),'saved mapping updates existing sidebar without remounting');
 assert(LabScopeLinks.serviceFor({url:links[0].url}).name==='My Grafana','older in-flight read cannot undo settings save');
 q('[data-add-domain]').click();const custom=rows()[1];change(custom,'domain','console.mycompany.com');change(custom,'domain-service','custom');change(custom,'tool-name','Internal operations');
 assert(!custom.querySelector('[data-custom-upload]').hidden,'custom icon choice exposes upload control');
 await upload(custom,'bad.svg','not an image','image/svg+xml');
 assert(custom._iconError&&custom.querySelector('[data-upload-status]').classList.contains('error'),'bad upload reports a recoverable error');
 await upload(custom,'team.svg','<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="20" fill="#e83e8c"/><path d="M30 64h68M64 30v68" stroke="white" stroke-width="14"/></svg>','image/svg+xml');
 assert(!custom._iconError&&custom._icon.startsWith('data:image/png;base64,'),'SVG upload is converted to an inert PNG');
 const image=new Image();image.src=custom._icon;await image.decode();assert(image.naturalWidth===64&&image.naturalHeight===64,'large icon resized to 64 pixels');
 failSave=true;q('form').requestSubmit();await until(()=>q('[data-message]').classList.contains('error'));
 assert(custom._icon&&custom.querySelector('[data-tool-name]').value==='Internal operations'&&!sidebar.querySelector('[data-link-custom]'),'failed save retains upload and leaves saved icons active');
 failSave=false;await save();
 const icon=sidebar.querySelector('[data-scope-link="1"] [data-link-custom]');assert(icon&&getComputedStyle(icon).backgroundSize==='contain'&&getComputedStyle(icon).backgroundImage.includes('data:image/png'),'custom icon renders fully in sidebar');
 assert(requests.at(-1).linkDomainMappings[1].icon===custom._icon,'uploaded PNG is stored with mapping');
 LabSettings.close();await LabSettings.open({section:'links'});await until(()=>rows().length===2);
 assert(rows()[1].querySelector('[data-icon-preview] img')&&rows()[1]._icon===''+cfg.linkDomainMappings[1].icon,'uploaded icon restored when settings reopen');
 q('[data-add-domain]').click();const parent=rows()[2];change(parent,'domain','mycompany.com');change(parent,'domain-service','grafana');change(parent,'subdomains',true);await save();
 assert(LabScopeLinks.serviceFor({url:links[1].url}).name==='Internal operations','specific custom hostname wins over broad domain');
 assert(LabScopeLinks.serviceFor({url:'https://another.mycompany.com/d/x'}).id==='grafana','include-subdomains mapping works');
 assert(!LabScopeLinks.serviceFor({url:'https://mycompany.com.evil.test/d/x'},false),'lookalike hostname cannot match');
 rows()[1].querySelector('[data-remove-domain]').click();await save();
 assert(!sidebar.querySelector('[data-link-custom]')&&sidebar.querySelector('[data-scope-link="1"] [data-link-service="grafana"]'),'removing custom mapping immediately falls back to parent rule');
 // Restore the custom mapping for the final screenshot and verify theme geometry.
 q('[data-add-domain]').click();const restored=rows().at(-1);change(restored,'domain','console.mycompany.com');change(restored,'domain-service','custom');change(restored,'tool-name','Internal operations');restored._icon=requests.find(body=>body.linkDomainMappings.some(row=>row.service==='custom')).linkDomainMappings.find(row=>row.service==='custom').icon;
 restored.querySelector('[data-domain-service]').dispatchEvent(new Event('change',{bubbles:true}));await save();fits();
 for(const light of [true,false]){document.documentElement.style.setProperty('--text-primary',light?'#1f2328':'#e6edf3');document.documentElement.style.setProperty('--bg-primary',light?'#ffffff':'#0d1117');document.documentElement.style.setProperty('--bg-secondary',light?'#f6f8fa':'#161b22');fits();}
 q('[data-domain-mappings]').scrollIntoView({block:'start'});
 document.getElementById('result').textContent='PASS domain overrides, real SVG upload/PNG resize, persisted custom icon, live sidebar updates, stale reads, failed saves, subdomain precedence, responsive settings';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    (tmp_path/'static').symlink_to(STATIC,target_is_directory=True)
    page=tmp_path/'domain-icons.html'
    page.write_text('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/css/lab-shell.css"><link rel="stylesheet" href="/static/css/settings-center.css"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#8b949e;--text-dim:#6e7681;--border:#30363d;--accent:#58a6ff}body{background:var(--bg-primary);font-family:system-ui}#links{width:280px}</style><pre id="result">PENDING</pre><section id="links" data-scope-links="/project" class="sidebar-scope-links"></section><script>window.LAB_LINK_SERVICES='+json.dumps(registry)+'</script><script src="/static/js/lib/scope-links.js"></script><script src="/static/js/lib/settings-center.js"></script><script>'+checks+'</script>')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(tmp_path)))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline
            time.sleep(.05)
        driver=tmp_path/'browser.mjs';driver.write_text((ROOT/'scripts/chrome-dump-auth.mjs').read_text().replace('width: 1440,','width: '+str(viewport)+','))
        result=subprocess.run([node,str(driver),str(profile),f'http://127.0.0.1:{server.server_port}/{page.name}',str(tmp_path/'dom.html'),str(tmp_path/'domain-icons.png')],capture_output=True,text=True,timeout=30,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
        server.shutdown();server.server_close();thread.join(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1].startswith('PASS '),result[1] if result else html[-1500:]
