"""Native Chrome exercises the shipped modal, Markdown and terminal entry points."""
from pathlib import Path
from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_ui import _js_between

STATIC=Path(__file__).resolve().parents[1]/'src/core/static'


def test_native_agent_history_search_preview_delegation_refresh_and_close(tmp_path):
    module=(STATIC/'js/lib/agent-work-history.js').read_text()
    css=(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/agent-work-history.css').read_text()
    libs=''.join('<script>'+ (STATIC/path).read_text().replace('</script','<\\/script')+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js','js/lib/markdown-content.js'])
    entry=_js_between('  function termOpenSessionDetails(name)', '  function _termRenderActiveSessionHeader()')
    setup=r'''
const terminal={name:'chief',label:'Chief of staff',tmux_socket:'owned',tmux_id:'$1',created:42,llm_controlled:true};
const child={...terminal,name:'analyst',tmux_id:'$2'};
let termSessions=[terminal,{...terminal,name:'shell',llm_controlled:false}],termCurrentSession='chief',renamed;
const termRenameSession=name=>renamed=name,explorerToast=message=>{throw Error(message)};
const makeFile=(id,path,operation='modified')=>({id,path,operation,reported:42});
let rows=[{id:'request',title:'Prepare report',request:'User petition',context:'Use authorized sources only',status:'working',created:42,
 terminal,files:[makeFile('report','/docs/report.md'),makeFile('removed','/docs/removed.txt','deleted')]},
 {id:'delegate',parent_id:'request',title:'Analyze revenue',request:'Return findings',context:'Use CSV',summary:'Validated',status:'finished',created:43,
 terminal:child,files:[makeFile('analysis','/analysis/revenue.py','created')]}];
let requests=[],refresh,blocked,resolvePreview;
window.setInterval=fn=>{refresh=fn;return 1};
window.fetch=async(url,options)=>{
 requests.push({url,options});
 if(url==='/api/term/work/history')return {ok:true,json:async()=>({assignments:structuredClone(JSON.parse(options.body).include_children?rows:rows.filter(row=>row.terminal.name==='chief'))})};
 const id=url.split('/').at(-1);
 if(id==='removed')return {ok:false,json:async()=>({detail:'This file was deleted or moved after it was reported'})};
 if(blocked===id)await new Promise(resolve=>resolvePreview=resolve);
 return {ok:true,json:async()=>id==='report'?{kind:'markdown',content:'# Report\n\n**Verified findings**\n\n![figure](figure%20one.png)\n\n<script>window.pwned=true<\/script>\n<img src=x onerror="window.pwned=true">'}:
  {kind:'text',content:'<script>unsafe</script>\nprint(42)'}};
};
const assert=(value,message)=>{if(!value)throw Error(message)};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const waitFor=async fn=>{for(let i=0;i<100&&!fn();i++)await tick();assert(fn(),'UI did not settle')};
'''
    checks=r'''
(async()=>{try{
 let prepared=0;LabAgentWorkHistory.configure({prepare:async()=>{prepared++},icon:()=>'<span>📝</span>'});
 document.getElementById('agent').focus();
 document.getElementById('agent').addEventListener('dblclick',()=>void termOpenSessionDetails('chief'));
 document.getElementById('agent').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
 await waitFor(()=>document.querySelector('.agent-work-preview article h1'));
 const overlay=()=>document.querySelector('.agent-work-overlay'),preview=()=>document.querySelector('[data-agent-work-preview]');
 assert(prepared===1&&preview().querySelector('h1').textContent==='Report','Cold Markdown rendering missing');
 assert(!window.pwned&&!preview().querySelector('script')&&!preview().querySelector('[onerror]'),'Unsafe content executed');
 assert(preview().querySelector('article img').getAttribute('src').includes('/asset?file=figure%20one.png'),'Relative image was not resolved from reported document');
 assert(document.querySelectorAll('[data-agent-file]').length===3,'Delegated work absent');
 assert(JSON.parse(requests[0].options.body).parent.tmux_id==='$1','Wrong terminal identity');
 const input=document.querySelector('[data-agent-work-search]');
 input.value='revenue created';input.dispatchEvent(new Event('input'));
 assert(document.querySelectorAll('[data-agent-file]').length===1&&document.querySelector('[data-agent-file]').dataset.agentFile==='analysis','Keyword search does not match assignment and operation');
 input.value='';input.dispatchEvent(new Event('input'));
 const toggle=document.querySelector('[data-agent-work-children]');toggle.checked=false;toggle.dispatchEvent(new Event('change'));
 await waitFor(()=>document.querySelectorAll('[data-agent-file]').length===2);
 toggle.checked=true;toggle.dispatchEvent(new Event('change'));
 await waitFor(()=>document.querySelectorAll('[data-agent-file]').length===3);
 await LabAgentWorkHistory.select('removed');assert(preview().textContent.includes('deleted or moved'),'Missing files hide their record');
 await LabAgentWorkHistory.select('analysis');assert(!preview().querySelector('script')&&preview().textContent.includes('<script>unsafe'),'Code was executed instead of escaped');
 // An unchanged history poll must not cancel an in-flight file preview.
 blocked='report';const pending=LabAgentWorkHistory.select('report');await waitFor(()=>resolvePreview);
 refresh();await tick();resolvePreview();await pending;blocked=null;
 assert(preview().querySelector('h1')?.textContent==='Report','Refresh cancelled preview');
 const summary=document.querySelector('[data-agent-assignment="delegate"]');summary.click();await tick();
 assert(preview().textContent.includes('Analyze revenue'),'Assignment brief missing');
 rows[1].summary='New validation';refresh();await tick();await tick();
 assert(preview().textContent.includes('New validation')&&!document.querySelector('[data-agent-group="delegate"]').open,'Refresh discarded brief/collapsed state');
 document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert(!overlay()&&document.activeElement.id==='agent','Escape/focus restoration failed');
 await termOpenSessionDetails('shell');assert(renamed==='shell','Plain shell rename changed');
 // Pending responses from a closed dialog cannot overwrite a replacement.
 blocked='report';resolvePreview=null;const old=termOpenCurrentDetails();await waitFor(()=>resolvePreview);
 const release=resolvePreview;LabAgentWorkHistory.close();rows=[];blocked=null;
 await termOpenCurrentDetails();release();await old;
 assert(preview().textContent.includes('The agent will record')&&!preview().querySelector('h1'),'Old request overwrote empty history');
 document.querySelector('[data-agent-work-close]').click();assert(!overlay(),'Corner close failed');
 // Leave a populated modal for the visual artifact.
 rows=[{id:'request',title:'Prepare report',request:'User petition',context:'Use authorized sources only',status:'finished',created:42,
 terminal,files:[makeFile('report','/docs/report.md')]}];
 await termOpenCurrentDetails();
 const box=overlay().querySelector('.doc-modal-box').getBoundingClientRect();
 assert(box.width>800&&box.height>600,'Document modal sizing incorrect');
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(error.stack)}})();
'''
    script=(setup+module+entry+checks).replace('</script','<\\/script')
    html='<!doctype html><meta charset="utf-8"><style>:root{--bg-primary:#0d1117;--bg-secondary:#161b22;--bg-tertiary:#21262d;--text-primary:#e6edf3;--text-secondary:#919ba6;--border:#30363d}body{font-family:system-ui;background:#0d1117;color:#e6edf3}'+css+'</style><button id="agent">Chief of staff</button>'+libs+'<script>'+script+'</script>'
    _check_project_html(tmp_path,html,focused=True,screenshot=True)


def test_native_narrow_agent_history_modal_and_keyboard_focus(tmp_path):
    import json
    css=(STATIC/'css/lab-shell.css').read_text()+(STATIC/'css/agent-work-history.css').read_text()
    module=(STATIC/'js/lib/agent-work-history.js').read_text()
    frame='<style>'+css+'</style><body><script>window.fetch=async()=>({ok:true,json:async()=>({assignments:[]})});'+module+'''
    LabAgentWorkHistory.open({name:'Narrow',tmux_socket:'owned',tmux_id:'$1',created:1}).then(()=>{
      const box=document.querySelector('.doc-modal-box').getBoundingClientRect();
      if(box.width>innerWidth||box.height>innerHeight)throw Error('Modal overflow');
      const search=document.querySelector('[data-agent-work-search]');search.focus();
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true}));
      if(!document.querySelector('.agent-work-overlay').contains(document.activeElement))throw Error('Focus escaped');
      parent.document.body.dataset.result='pass';
    }).catch(error=>{parent.document.body.dataset.result='fail';parent.document.body.append(error.stack)});
    </script>'''
    html='<iframe style="width:390px;height:800px;border:0"></iframe><script>document.querySelector("iframe").srcdoc='+json.dumps(frame).replace('</script','<\\/script')+';</script>'
    _check_project_html(tmp_path,html,focused=True)
