"""Real Chrome exercises settings, terminal context menus and captured launches."""
from html import escape

import pytest

from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_subtabs import GROUPS
from .test_frontend_terminal_ui import _js_between, _run_node, LAB_APP


def test_default_icon_inheritance_follows_parent_changes_and_respects_overrides():
    script = (LAB_APP.parent / 'lib/terminal-automations.js').read_text()
    result = _run_node('const window={};\n' + script + r'''
const main={logical_name:'main',automation_appearance:{icon:{service:'github'},color:'#3fb950',role:'main'}};
const child={logical_name:'child',automation_appearance:{icon:{builtin:'terminal'},color:null,role:'child',inherit_icon:true}};
const nested={logical_name:'nested'},rows=new Map([main,child,nested].map(row=>[row.logical_name,row])),parents={child:'main',nested:'child'};
const look=row=>LabTerminalAutomations.inheritedAppearance(row,rows,parents);
const LabTerminalAutomations=window.LabTerminalAutomations;
if(look(child).icon.service!=='github'||look(nested).color!==null)throw Error('default children inherit the current main icon with white text');
main.automation_appearance.icon={emoji:'🚀'};
if(look(child).icon.emoji!=='🚀'||look(nested).icon.emoji!=='🚀')throw Error('inherited icons follow later parent changes');
child.automation_appearance={icon:{emoji:'📋'},color:'#58a6ff',role:'child',inherit_icon:false};
if(look(child).color!=='#58a6ff'||look(nested).icon.emoji!=='📋')throw Error('explicit overrides define a child branch icon independently');
console.log(JSON.stringify({pass:true}));
''')
    assert result['pass']


@pytest.mark.parametrize('width', [1440, 390])
def test_native_workspace_automation_settings_picker_and_child_adoption(tmp_path, width):
    static = LAB_APP.parents[1]
    settings = (static / 'js/lib/settings-center.js').read_text()
    automations = (static / 'js/lib/terminal-automations.js').read_text()
    css = (static / 'css/settings-center.css').read_text()
    template = (static.parent / 'templates/index.html').read_text()
    new_button = next(line for line in template.splitlines() if 'id="termNewAutomation"' in line)
    adapter = _js_between('  async function _termLaunchAutomation(', '  async function _termPasteTaskContext(')
    setup = r'''
localStorage.clear();
window.LAB_IS_ADMIN=true;
const scope={key:'/fixture/demo',id:'demo',path:'/fixture/demo',label:'Demo',vault:'one',kind:'workspace'};
let activeWorkspace='demo',activeObjective='objective',activeTask='task',tasksAvailable=true;
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
let adopted=[],activated=[],directRequests=[],launchRequests=[],objectiveReloads=[],launchCalls=0,previewCalls=0,saved=0,failPreview=false,partial=false,hold=false,release;
window.LabObjectives={terminalMain:t=>t?.name==='main'?{kind:'workflow'}:null,
 sameTerminalObjective:()=>true,taskForTerminal:t=>({title:'Task'}),
 terminalLaunchContext:()=>activeObjective?({id:activeObjective,path:'/fixture/objective',context:{workspace_id:'demo',path:scope.path,vault:scope.vault},task:activeTask?{id:activeTask,title:'Active task'}:null}):null,
 automationTasks:()=>tasksAvailable?[{id:'task',title:'Active task',objective_id:'objective',objective_name:'Objective',path:'/fixture/objective'},{id:'another-task',title:'Another WIP',objective_id:'objective',objective_name:'Objective',path:'/fixture/objective'}]:[],
 load:async context=>{if(context)objectiveReloads.push(context)},
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
  assert(body.workspace_id==='demo'&&body.vault==='one','captured workspace scope');
  assert(body.objective_id==='objective'&&['task','another-task'].includes(body.task_id),'every automation explicitly owns a WIP task');
  if(body.parent)assert(body.parent===parent.name,'captured parent');
  else {assert(body.cwd==='/fixture/objective'||body.cwd===scope.path,'direct launch uses its own captured folder');directRequests.push(body);}
  const recipe=catalogs.demo.automations.find(row=>row.id===body.automation_id);
  if(body.preview){previewCalls++;if(failPreview)return {ok:false,json:async()=>({detail:'Missing folder'})};
   data={name:recipe.name,launch_delay_seconds:recipe.launch_delay_seconds,steps:recipe.steps.map(row=>({...row,cwd:row.cwd?(body.cwd||'/fixture/checkout')+'/'+row.cwd:(body.cwd||'/fixture/checkout')}))};
  }else{
   launchCalls++;launchRequests.push(body);if(hold)await new Promise(r=>release=r);
   data={sessions:recipe.steps.slice(0,partial?1:undefined).map((row,index)=>({name:'run-'+launchCalls+'-'+index,logical_name:'run-'+launchCalls+'-'+index,session_id:'uuid-'+launchCalls+'-'+index,label:row.label,cwd:row.cwd?(body.cwd||'/fixture/checkout')+'/'+row.cwd:(body.cwd||'/fixture/checkout'),workspace_id:'demo'})),...(partial?{error:'Frontend: spawn failed'}:{})};
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
 assert(q('[data-launch-delay]').value==='5','new automations default to five seconds');
 fill('[data-launch-delay]','-1');assert(!q('[data-launch-delay]').checkValidity(),'negative delays rejected');
 fill('[data-launch-delay]','2.5');
 assert(q('[data-icon-choice]').value==='terminal'&&q('[data-look-color]').value==='#3fb950','main defaults to outlined terminal and green');
 const mainChoice=q('[data-icon-choice]');mainChoice.value='service:github';mainChoice.dispatchEvent(new Event('change',{bubbles:true}));
 assert(q('[data-look-icon] [data-link-service=github]'),'main icon preview uses the selected service');
 mainChoice.value='image';mainChoice.dispatchEvent(new Event('change',{bubbles:true}));
 const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const bytes=Uint8Array.from(atob(canvas.toDataURL('image/png').split(',')[1]),c=>c.charCodeAt(0));
 const transfer=new DataTransfer();transfer.items.add(new File([bytes],'terminal.png',{type:'image/png'}));const upload=q('[data-icon-file]');upload.files=transfer.files;upload.dispatchEvent(new Event('change',{bubbles:true}));
 await until(()=>q('[data-look-icon] img'));
 assert(q('[data-look-icon] img').src.startsWith('data:image/png;base64,'),'uploaded PNG previews after decoding');
 mainChoice.value='service:github';mainChoice.dispatchEvent(new Event('change',{bubbles:true}));
 q('[data-add-step]').click();const steps=[...document.querySelectorAll('[data-step]')];
 steps[1].querySelector('[data-label]').value='Frontend';steps[1].querySelector('[data-cwd]').value='frontend';steps[1].querySelector('[data-command]').value='npm run dev';
 assert(steps[1].querySelector('[data-icon-choice]').value==='inherit'&&steps[1].querySelector('[data-look-default]').checked&&steps[1].querySelector('[data-look-icon] [data-link-service=github]'),'children default to inherited icon and white');
 const childChoice=steps[1].querySelector('[data-icon-choice]');childChoice.value='emoji:🚀';childChoice.dispatchEvent(new Event('change',{bubbles:true}));
 const childColor=steps[1].querySelector('[data-look-color]');childColor.value='#58a6ff';childColor.dispatchEvent(new Event('input',{bubbles:true}));
 q('[data-add-automation]').click();const diagnostic=[...document.querySelectorAll('[data-automation]')].at(-1);
 diagnostic.querySelector('[data-name]').value='Diagnostics';diagnostic.querySelector('[data-label]').value='Inspect';diagnostic.querySelector('[data-command]').value='printf diagnostics';
 diagnostic.querySelector('[data-launch-delay]').value='0';
 q('.settings-form').requestSubmit();await until(()=>q('[data-message]').textContent==='Saved');
 assert(saved===1&&launchCalls===0&&previewCalls===0,'saving creates no terminals or launch previews');
 LabSettings.close();await LabSettings.open({scope,section:'automations'});await until(()=>q('[data-command]'));
 assert(q('#labSettingsCenter [data-name]').value==='Development'&&document.querySelectorAll('[data-step]').length===3,'saved recipes restored');
 assert(q('[data-launch-delay]').value==='2.5'&&[...document.querySelectorAll('[data-launch-delay]')][1].value==='0','custom and disabled delays survive reopening settings');
 assert(q('[data-icon-choice]').value==='service:github'&&catalogs.demo.automations[0].steps[0].icon===null&&catalogs.demo.automations[0].steps[0].color===null,'overall icon and inherited defaults survive save');
 assert(catalogs.demo.automations[0].steps[1].icon.emoji==='🚀'&&catalogs.demo.automations[0].steps[1].color==='#58a6ff','child icon and color overrides survive save');
 q('[data-down]').click();assert(q('[data-label]').value==='Frontend','step order editable');q('[data-up]:not(:disabled)').click();assert(q('[data-label]').value==='Logs','step order restored');
 LabSettings.close();
 await launchMenu();await until(()=>!q('[data-launch]').disabled);
 assert(q('[data-preview]').textContent.includes('/fixture/checkout/frontend')&&q('[data-preview]').textContent.includes("<log>"),'escaped commands and resolved paths reviewed');
 assert(!q('[data-preview] log'),'command text never interpreted as markup');
 assert(q('[data-hint]').textContent.includes('2.5 seconds between launches'),'saved delay appears in the launch preview');
 assert(q('[data-choice]').options.length===2,'choose among saved automations');q('[data-choice]').value=catalogs.demo.automations[1].id;q('[data-choice]').dispatchEvent(new Event('change'));await until(()=>q('[data-preview]').textContent.includes('diagnostics'));assert(q('[data-preview]').textContent.includes('Inspect')&&!q('[data-preview]').textContent.includes('Frontend'),'selection previews only chosen group');
 q('#termAutomationLauncher [data-close]').click();assert(launchCalls===0&&termSessions.length===1,'cancel launches nothing');
 await launchMenu();await until(()=>!q('[data-launch]').disabled);
 hold=true;q('[data-launch]').click();q('[data-launch]').click();await until(()=>!!release);assert(launchCalls===1,'double-click starts once');release();
 await until(()=>!q('#termAutomationLauncher'));hold=false;
 assert(termSessions.length===3&&adopted.length===0&&launchRequests[0].task_id==='task','server owns the selected task without browser reassignment');
 assert(q('#termAutomationLauncher')===null,'successful task-bound launch closes the picker');
 let state=_termReadGroupState();assert(state.tabParents['run-1-0']==='parent'&&state.tabParents['run-1-1']==='run-1-0','durable child hierarchy');
 assert(activated[0]==='run-1-0','first logs selected');termCurrentSession='parent';termRenderSessionList();
 assert(document.querySelectorAll('.term-subtab-children[hidden] .sess').length===2,'inactive children fold below parent');
 parent.name='main';parent.logical_name='main';termCurrentSession='main';termSessions=[parent];termRenderSessionList();
 await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-launch]').click();await until(()=>!q('#termAutomationLauncher'));
 assert(_termReadGroupState().tabParents['run-2-0']==='main','fixed workspace main supports automation children');
 failPreview=true;await launchMenu();await until(()=>q('[data-status]').textContent==='Missing folder');assert(q('[data-launch]').disabled,'invalid path blocks launch');q('#termAutomationLauncher [data-close]').click();failPreview=false;
 await launchMenu();await until(()=>!q('[data-launch]').disabled);activeWorkspace='other';q('[data-launch]').click();assert(launchCalls===2&&q('[data-launch]').disabled,'navigation blocks stale launch');q('#termAutomationLauncher [data-close]').click();activeWorkspace='demo';
 partial=true;await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-launch]').click();await until(()=>q('[data-status]')?.textContent.includes('spawn failed'));
 assert(termSessions.some(t=>t.name==='run-3-0')&&q('[data-launch]').disabled,'partial launch retains child and prevents replay');q('#termAutomationLauncher [data-close]').click();partial=false;

 // + New creates the whole family, with no starter terminal or primary chooser.
 termSessions=[];termCurrentSession=null;termRenderSessionList();
 const directMenu=async()=>{q('#termNewAutomation').click();await until(()=>q('[data-launch]')?.disabled===false);};
 await directMenu();
 assert(q('[data-preview] strong').textContent==='1. Logs · Primary'&&q('[data-preview]').textContent.includes('/fixture/objective/frontend'),'first defined step is previewed as primary in the active task folder');
 assert(q('.term-automation-body').textContent.includes('Active task'),'captured task shown before launching');
 q('[data-launch]').click();await until(()=>!q('#termAutomationLauncher'));
 assert(termSessions.length===2&&termCurrentSession==='run-4-0','direct launch creates only its two terminals and selects the first');
 state=_termReadGroupState();
 assert(!state.tabParents['run-4-0']&&state.tabParents['run-4-1']==='run-4-0','the first step owns the automation family');
 assert(state.order.indexOf('s:run-4-0')+1===state.order.indexOf('s:run-4-1'),'recipe order is preserved');
 assert(directRequests.every(row=>!row.parent&&row.objective_id==='objective'&&row.task_id==='task'),'API captures the exact primary task without a parent terminal');
 assert(objectiveReloads.at(-1).workspace_id==='demo','server-side task assignment is refreshed');
 await directMenu();activeTask='another-task';q('[data-launch]').click();
 assert(launchCalls===4&&q('[data-launch]').disabled,'switching task cancels a pending direct launch');q('[data-close]').click();activeTask='task';
 // A navigation during creation keeps adoption in the captured workspace and
 // does not select the new group over the user's later choice.
 await directMenu();hold=true;release=null;const selectedBefore=activated.length;
 q('[data-launch]').click();await until(()=>!!release);activeWorkspace='other';activeTask='another-task';release();
 await until(()=>!q('#termAutomationLauncher'));hold=false;
 const originalState=_termReadGroupState('one::demo');
 assert(originalState.tabParents['run-5-1']==='run-5-0'&&!originalState.tabParents['run-5-0'],'late direct result retains original hierarchy');
 assert(activated.length===selectedBefore&&!termSessions.some(row=>row.name==='run-5-0'),'late launch cannot hijack another workspace');
 assert(directRequests.at(-1).task_id==='task','launch request keeps the original task');
 activeWorkspace='demo';activeTask='task';
 // Without a selected task, an explicit WIP choice is required.
 activeObjective=null;q('#termNewAutomation').click();await until(()=>q('[data-choice]')?.disabled===false);
 assert(q('[data-launch]').disabled&&q('[data-task-choice]').value===''&&q('[data-task-choice]').options.length===3,'workspace launch requires one of the available WIP tasks');
 q('[data-task-choice]').value='1';q('[data-task-choice]').dispatchEvent(new Event('change'));await until(()=>!q('[data-launch]').disabled);
 q('[data-launch]').click();await until(()=>!q('#termAutomationLauncher'));
 assert(directRequests.at(-1).objective_id==='objective'&&directRequests.at(-1).task_id==='another-task'&&directRequests.at(-1).cwd==='/fixture/objective','chosen WIP task owns the workspace launch');
 assert(_termReadGroupState().tabParents['run-6-1']==='run-6-0','workspace-only automation also makes its own primary');
 tasksAvailable=false;await _termLaunchAutomation();assert(q('[data-launch]').disabled&&q('[data-status]').textContent.includes('No In progress tasks')&&launchCalls===6,'no WIP tasks blocks launching');q('[data-close]').click();tasksAvailable=true;
 activeObjective='objective';termSessions=[parent];termCurrentSession=parent.name;termRenderSessionList();
 await launchMenu();await until(()=>!q('[data-launch]').disabled);q('[data-configure]').click();await until(()=>q('[data-remove-automation]'));document.querySelectorAll('[data-remove-automation]').forEach(button=>button.click());q('.settings-form').requestSubmit();await until(()=>q('[data-message]').textContent==='Saved');LabSettings.close();
 assert(catalogs.demo.automations.length===0,'remove saved automation');
 await _termLaunchAutomation(parent); // Empty catalog: asynchronous open returns after loading.
 assert(q('[data-launch]').disabled&&q('[data-status]').textContent.includes('settings'),'empty launcher routes to settings');
 assert(q('#termAutomationLauncher').getBoundingClientRect().width<=innerWidth,'picker fits viewport');
 document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(document.createTextNode(error.stack));});
'''
    html = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width"><style>{css}</style></head><body>
<div id="termNewPicker">{new_button}</div><div id="termSessionList"></div><div id="termGroupMenu" class="term-group-menu"></div>
<script>{setup}</script><script>{GROUPS}</script><script>{adapter}</script><script>{automations}</script><script>{settings}</script><script>{actions}</script></body></html>'''
    # A narrow native frame exercises the same dialog/media-query layout.
    if width == 390:
        html = f'''<!doctype html><body><iframe style="width:390px;height:900px;border:0" srcdoc="{escape(html, quote=True)}"></iframe><script>
const timer=setInterval(()=>{{const inner=document.querySelector('iframe').contentDocument;if(inner.body.dataset.result){{document.body.dataset.result=inner.body.dataset.result;if(inner.body.dataset.result==='fail')document.body.append(inner.body.textContent);clearInterval(timer);}}}},20);
</script></body>'''
    _check_project_html(tmp_path, html)
