"""Real Chrome exercises settings, terminal context menus and captured launches."""
from html import escape

import pytest

from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_subtabs import GROUPS
from .test_frontend_terminal_ui import _js_between, LAB_APP


@pytest.mark.parametrize('width', [1440, 390])
def test_native_workspace_automation_settings_picker_and_child_adoption(tmp_path, width):
    static = LAB_APP.parents[1]
    settings = (static / 'js/lib/settings-center.js').read_text()
    automations = (static / 'js/lib/terminal-automations.js').read_text()
    css = (static / 'css/settings-center.css').read_text()
    adapter = _js_between('  async function _termLaunchAutomation(', '  async function _termPasteTaskContext(')
    setup = r'''
localStorage.clear();
window.LAB_IS_ADMIN=true;
const scope={key:'/fixture/demo',id:'demo',path:'/fixture/demo',label:'Demo',vault:'one',kind:'workspace'};
let activeWorkspace='demo',activeObjective='objective',activeTask='task';
const _TERM_GROUPS_KEY='testGroups',_TERM_GROUP_COLORS=['#58a6ff'];let _termGroupMenuOutside=null;
const _termSessionsKey=(id,vault)=>vault+'::'+id,_termActiveWorkspaceId=()=>activeWorkspace,_termVaultId=()=> 'one';
const _termHomeSection=()=>null,_termSaveHomeAssociation=()=>{throw Error('not Home')};
let termCurrentWorkspaceId='demo',termCurrentSession='parent',termSessionOrientation='vertical',termWipOnly=true;
const parent={name:'parent',logical_name:'parent',session_id:'primary',label:'Task terminal',cwd:'/fixture/checkout'};
let termSessions=[parent];
const termSessEsc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _termSessionDisplay=t=>t.label,_termSessionMeta=name=>termSessions.find(t=>t.name===name);
const explorerToast=()=>{},_termInvalidateSessionReads=()=>{},_termSessionsCache=new Map();
const termSetAutoSpawnEnabled=async(id,on,vault)=>assert(id==='demo'&&on&&vault==='one','captured restoration preference');
let adopted=[],activated=[],launchCalls=0,previewCalls=0,saved=0,failPreview=false,partial=false,hold=false,release;
window.LabObjectives={terminalMain:t=>t?.name==='main'?{kind:'workflow'}:null,
 sameTerminalObjective:()=>true,taskForTerminal:t=>({title:'Task'}),
 terminalLaunchContext:()=>({id:activeObjective,task:{id:activeTask}}),
 childTerminalAssociation:()=>({context:{path:scope.path,workspace_id:scope.id,vault:scope.vault},objective_id:'objective',view:'tasks'}),
 associateNewTerminal:async(t,a)=>{adopted.push({t,a});},terminalExpanded:()=>undefined};
const _termActivateTab=async name=>{activated.push(name);termCurrentSession=name;termRenderSessionList();};
const _termRefreshSessionsForWorkspaceId=async()=>termRenderSessionList();
window.LabSettingsBridge={initialScopes:()=>[scope],currentScope:()=>scope};
let catalogs={demo:{revision:'zero',automations:[]},other:{revision:'other',automations:[]}};
window.fetch=async(url,options={})=>{
 const body=options.body&&JSON.parse(options.body),parsed=new URL(url,'http://fixture');
 let data;
 if(url==='/api/settings/global')data={defaultAgent:'codex',autopilot:{},theme:'dark'};
 else if(url==='/api/agents/available')data={codex:true};
 else if(url==='/api/vaults/workspaces')data={vaults:[]};
 else if(parsed.pathname==='/api/term/automations'){
  const id=body?.workspace_id||parsed.searchParams.get('workspace_id');
  if(body){saved++;catalogs[id]={revision:'revision-'+saved,automations:body.automations};}
  data=catalogs[id];
 }else if(url==='/api/term/automations/launch'){
  assert(body.workspace_id==='demo'&&body.vault==='one'&&body.parent===parent.name,'captured parent scope');
  const recipe=catalogs.demo.automations.find(row=>row.id===body.automation_id);
  if(body.preview){previewCalls++;if(failPreview)return {ok:false,json:async()=>({detail:'Missing folder'})};
   data={name:recipe.name,steps:recipe.steps.map(row=>({...row,cwd:row.cwd?'/fixture/checkout/'+row.cwd:'/fixture/checkout'}))};
  }else{
   launchCalls++;if(hold)await new Promise(r=>release=r);
   data={sessions:recipe.steps.slice(0,partial?1:undefined).map((row,index)=>({name:'run-'+launchCalls+'-'+index,logical_name:'run-'+launchCalls+'-'+index,session_id:'uuid-'+launchCalls+'-'+index,label:row.label,cwd:row.cwd?'/fixture/checkout/'+row.cwd:'/fixture/checkout',workspace_id:'demo'})),...(partial?{error:'Frontend: spawn failed'}:{})};
  }
 }else throw Error('Unexpected request '+url);
 return {ok:true,json:async()=>structuredClone(data)};
};
const assert=(value,label)=>{if(!value)throw Error(label)};
const until=async fn=>{for(let i=0;i<250;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Timed out '+fn);};
window.confirm=()=>true;
'''
    actions = r'''
function termRenderSessionList(){
 const state=_termReadGroupState(),render=_termSubtabRenderer(state,termSessions,(t,i)=>`<span class="sess" data-name="${t.name}" data-logical="${t.logical_name}" role="tab">${t.label}</span>`);
 document.getElementById('termSessionList').innerHTML=_termArrangeSubtabRows(termSessions,state).map(render).join('');
 document.querySelectorAll('.sess').forEach(node=>node.oncontextmenu=event=>{event.preventDefault();termOpenTabMenu(node.dataset.name,node);});
}
const q=selector=>document.querySelector(selector);
const fill=(selector,value)=>{const node=q('#labSettingsCenter '+selector);node.value=value;node.dispatchEvent(new Event('input',{bubbles:true}));};
const launchMenu=async()=>{q('[data-name="'+parent.name+'"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}));assert(q('[data-action="automation"]'),'right-click launch action');q('[data-action="automation"]').click();await until(()=>q('#termAutomationLauncher [data-choice]')?.disabled===false);};
(async()=>{
 termRenderSessionList();
 await LabSettings.open({scope,section:'automations'});
 await until(()=>q('[data-add-automation]'));
 q('[data-add-automation]').click();fill('[data-name]','Development');fill('[data-label]','Logs');fill('[data-command]',"printf '<log>\\n'");
 q('[data-add-step]').click();const steps=[...document.querySelectorAll('[data-step]')];
 steps[1].querySelector('[data-label]').value='Frontend';steps[1].querySelector('[data-cwd]').value='frontend';steps[1].querySelector('[data-command]').value='npm run dev';
 q('[data-add-automation]').click();const diagnostic=[...document.querySelectorAll('[data-automation]')].at(-1);
 diagnostic.querySelector('[data-name]').value='Diagnostics';diagnostic.querySelector('[data-label]').value='Inspect';diagnostic.querySelector('[data-command]').value='printf diagnostics';
 q('.settings-form').requestSubmit();await until(()=>q('[data-message]').textContent==='Saved');
 assert(saved===1&&launchCalls===0&&previewCalls===0,'saving creates no terminals or launch previews');
 LabSettings.close();await LabSettings.open({scope,section:'automations'});await until(()=>q('[data-command]'));
 assert(q('#labSettingsCenter [data-name]').value==='Development'&&document.querySelectorAll('[data-step]').length===3,'saved recipes restored');
 q('[data-down]').click();assert(q('[data-label]').value==='Frontend','step order editable');q('[data-up]:not(:disabled)').click();assert(q('[data-label]').value==='Logs','step order restored');
 LabSettings.close();
 await launchMenu();await until(()=>!q('[data-launch]').disabled);
 assert(q('[data-preview]').textContent.includes('/fixture/checkout/frontend')&&q('[data-preview]').textContent.includes("<log>"),'escaped commands and resolved paths reviewed');
 assert(!q('[data-preview] log'),'command text never interpreted as markup');
 assert(q('[data-choice]').options.length===2,'choose among saved automations');q('[data-choice]').value=catalogs.demo.automations[1].id;q('[data-choice]').dispatchEvent(new Event('change'));await until(()=>q('[data-preview]').textContent.includes('diagnostics'));assert(q('[data-preview]').textContent.includes('Inspect')&&!q('[data-preview]').textContent.includes('Frontend'),'selection previews only chosen group');
 q('#termAutomationLauncher [data-close]').click();assert(launchCalls===0&&termSessions.length===1,'cancel launches nothing');
 await launchMenu();await until(()=>!q('[data-launch]').disabled);
 hold=true;q('[data-launch]').click();q('[data-launch]').click();await until(()=>!!release);assert(launchCalls===1,'double-click starts once');release();
 await until(()=>!q('#termAutomationLauncher'));hold=false;
 assert(termSessions.length===3&&adopted.length===2,'two created children adopted');
 assert(adopted.every(row=>!row.a.task_id&&row.a.objective_id==='objective'),'children inherit parent context without taking primary task ownership');
 let state=_termReadGroupState();assert(state.tabParents['run-1-0']==='parent'&&state.tabParents['run-1-1']==='parent','durable child hierarchy');
 assert(activated[0]==='run-1-0','first logs selected');termCurrentSession='parent';termRenderSessionList();
 assert(document.querySelectorAll('.term-subtab-children[hidden] .sess').length===2,'inactive children fold below parent');
 parent.name='main';parent.logical_name='main';termCurrentSession='main';termSessions=[parent];termRenderSessionList();
 await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-launch]').click();await until(()=>!q('#termAutomationLauncher'));
 assert(_termReadGroupState().tabParents['run-2-0']==='main','fixed workspace main supports automation children');
 failPreview=true;await launchMenu();await until(()=>q('[data-status]').textContent==='Missing folder');assert(q('[data-launch]').disabled,'invalid path blocks launch');q('#termAutomationLauncher [data-close]').click();failPreview=false;
 await launchMenu();await until(()=>!q('[data-launch]').disabled);activeWorkspace='other';q('[data-launch]').click();assert(launchCalls===2&&q('[data-launch]').disabled,'navigation blocks stale launch');q('#termAutomationLauncher [data-close]').click();activeWorkspace='demo';
 partial=true;await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-launch]').click();await until(()=>q('[data-status]')?.textContent.includes('spawn failed'));
 assert(termSessions.some(t=>t.name==='run-3-0')&&q('[data-launch]').disabled,'partial launch retains child and prevents replay');q('#termAutomationLauncher [data-close]').click();partial=false;
 await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-configure]').click();await until(()=>q('[data-remove-automation]'));document.querySelectorAll('[data-remove-automation]').forEach(button=>button.click());q('.settings-form').requestSubmit();await until(()=>q('[data-message]').textContent==='Saved');LabSettings.close();
 assert(catalogs.demo.automations.length===0,'remove saved automation');
 await _termLaunchAutomation(parent); // Empty catalog: asynchronous open returns after loading.
 assert(q('[data-launch]').disabled&&q('[data-status]').textContent.includes('settings'),'empty launcher routes to settings');
 assert(q('#termAutomationLauncher').getBoundingClientRect().width<=innerWidth,'picker fits viewport');
 document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(document.createTextNode(error.stack));});
'''
    html = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width"><style>{css}</style></head><body>
<div id="termSessionList"></div><div id="termGroupMenu" class="term-group-menu"></div>
<script>{setup}</script><script>{GROUPS}</script><script>{adapter}</script><script>{automations}</script><script>{settings}</script><script>{actions}</script></body></html>'''
    # A narrow native frame exercises the same dialog/media-query layout.
    if width == 390:
        html = f'''<!doctype html><body><iframe style="width:390px;height:900px;border:0" srcdoc="{escape(html, quote=True)}"></iframe><script>
const timer=setInterval(()=>{{const inner=document.querySelector('iframe').contentDocument;if(inner.body.dataset.result){{document.body.dataset.result=inner.body.dataset.result;if(inner.body.dataset.result==='fail')document.body.append(inner.body.textContent);clearInterval(timer);}}}},20);
</script></body>'''
    _check_project_html(tmp_path, html)
