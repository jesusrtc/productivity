"""Native task customization keeps service icons, colors and session ownership."""
from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_ui import LAB_APP, LAB_SHELL_CSS, _js_between


def test_task_icon_picker_and_shared_color_palette_in_chrome(tmp_path):
    static = LAB_APP.parents[1]
    app = LAB_APP.read_text()
    palette = app[app.index('  const SIDEBAR_SCOPE_COLORS ='):app.index('  const SIDEBAR_FILE_CONFIG_DEFAULTS =')]
    setup = r'''
const assert=(ok,label)=>{if(!ok)throw Error(label)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out '+fn)};
let requests=[],refreshes=0;
const task={id:'task',title:'Review',document_id:'details',tab_id:'tab',status:'in_progress',done:false,children:[],assets:[{id:'folder',folder:{root:'/checkout',path:'.'}}],recurrence:{unit:'week',every:1}};
const owner={id:'one',name:'Project',purpose:'',color:'#58a6ff',tasks:[task],worktrees:[{id:'tree',path:'/checkout',repo:'/checkout',label:'feature/review',kind:'worktree',color:'#58a6ff'}],resources:[{id:'details',title:'Tasks',kind:'document',path:'Tasks.md',task_document:true},{id:'grafana-one',title:'Grafana One',kind:'link',url:'https://grafana.example.com/one'},{id:'grafana-two',title:'Grafana Two',kind:'link',url:'https://grafana.example.com/two'}]};
let payload={enabled:true,revision:'one',focused:['one'],objectives:[owner],terminal_links:{primary:{objective_id:'one',task_id:'task'}},task_terminals:true};
window.fetch=async(url,options)=>{
 if(options?.method==='POST'){const body=JSON.parse(options.body);requests.push(body);Object.assign(task,{icon:body.action.icon,terminal_color:body.action.terminal_color});payload.revision+='x';}
 return {ok:true,json:async()=>structuredClone(payload)};
};
const primary={name:'primary',session_id:'primary',logical_name:'primary'};
const child={name:'child',session_id:'child',logical_name:'child'};
const termSessions=[primary,child];
const termSessEsc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _termActiveWorkspaceId=()=> 'demo',_termRecentScopeKey=()=> 'demo';
let termCurrentWorkspaceId='demo',termCurrentSession='primary';
const _termSessionDisplay=s=>s.logical_name,_termSessionVisual=()=>({kind:'terminal',badge:'Terminal',icon:'💻'});
const _termSessionRecentMeta=()=>null,_termSessionIsWorking=()=>false,_termSessionContext=()=>({label:'Requests'}),_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}',_termSessionAssociationHtml=()=>'';
const termDeadSessions=new Set(),_termReadGroupState=()=>({}),_termSubtabParents=()=>({child:'primary'});
'''
    checks = r'''
(async()=>{
 LabObjectives.connect({context:()=>({workspace_id:'demo',path:'/workspace',vault:'fixture'}),sessions:()=>termSessions,parentTerminal:s=>s.name==='child'?primary:null,scopeColorPalette:()=>SIDEBAR_SCOPE_COLORS,refreshTerminals:()=>refreshes++});
 await LabObjectives.load();
 const sidebar=document.querySelector('[data-objectives-sidebar]');
 assert(sidebar.querySelector('.objective-sidebar-task-status').textContent==='🚧','WIP uses construction badge');
 assert(sidebar.querySelector('.objective-task-recurring').textContent==='🔄','recurring task identifier');
 const open=()=>sidebar.querySelector('.objective-sidebar-task-status').click();
 const picker=()=>document.querySelector('.objective-task-icon-picker');
 open();
 assert(picker()?.open,'click on badge opens picker');
 assert(picker().querySelector('[aria-label="Asset icons"]').compareDocumentPosition(picker().querySelector('[aria-label="Suggested emojis"]'))&Node.DOCUMENT_POSITION_FOLLOWING,'asset icons first');
 assert(picker().querySelectorAll('[data-link-service=grafana]').length===1,'distinct asset service icons');
 const github=picker().querySelector('[data-pick-task-icon="'+CSS.escape(JSON.stringify({service:'github'}))+'"]');
 assert(github,'GitHub selectable without GitHub asset');github.click();
 picker().querySelector('[data-task-text-color]').click();
 const colorPicker=document.querySelector('.sidebar-scope-palette');
 assert(colorPicker?.open&&colorPicker.querySelectorAll('[data-color]').length===SIDEBAR_SCOPE_COLORS.length,'same worktree palette component');
 colorPicker.querySelector('[data-color="#ff7b72"]').click();
 assert(picker().querySelector('[data-task-color-preview]').style.color==='rgb(255, 123, 114)','color preview');
 assert(!requests.length,'preview does not mutate');
 picker().querySelector('[type=submit]').click();await until(()=>!picker());
 assert(requests.length===1&&requests[0].vault==='fixture'&&requests[0].action.icon.service==='github'&&requests[0].action.terminal_color==='#ff7b72','one scoped customization save');
 assert(task.assets.length===1&&!owner.resources.some(r=>r.url?.includes('github')),'icon selection never attaches or creates an asset');
 await LabObjectives.load(undefined,true);
 assert(sidebar.querySelector('button:last-child [data-link-service=github]'),'saved sidebar icon');
 const panel=document.getElementById('termPanel'),switcher=document.getElementById('termSessionSwitcher'),list=document.getElementById('termSessionList');
 const merged={...child,display_main:{parent:'primary',identity:primary,color:'#58a6ff'}};
 list.innerHTML=[_termSessionPillHtml(primary,0),_termSessionPillHtml(child,1),_termSessionPillHtml(merged,2),_termTaskPlaceholderHtml({objective_placeholder:true,objective_id:'one',task_id:'task',label:'Review'})].join('');
 for(const horizontal of [false,true]){
  panel.classList.toggle('term-sessions-horizontal',horizontal);
  panel.classList.toggle('term-sessions-full',!horizontal);switcher.classList.remove('term-tabs-open');
  assert([...list.querySelectorAll('.sess-task-icon')].every(n=>getComputedStyle(n).display!=='none'&&n.querySelector('[data-link-service=github]')),'compact custom GitHub on primary, inherited, merged and dormant rows');
  if(horizontal)panel.classList.add('term-sessions-full');else switcher.classList.add('term-tabs-open');
  assert([...list.querySelectorAll('.sess-label')].every(n=>getComputedStyle(n).color==='rgb(255, 123, 114)'),'chosen text color across all terminal rows');
  assert([...list.querySelectorAll('.objective-task-worktree-name')].every(n=>getComputedStyle(n).color==='rgb(255, 123, 114)'),'text override wins over worktree name color');
 }
 open();picker().querySelector('[data-pick-task-icon="'+CSS.escape(JSON.stringify({emoji:'💡'}))+'"]').click();picker().querySelector('[data-cancel]').click();
 assert(requests.length===1&&task.icon.service==='github','cancel preserves saved icon and color');
 open();picker().querySelector('[data-pick-task-icon=null]').click();picker().querySelector('[data-task-default-color]').click();picker().querySelector('[type=submit]').click();await until(()=>!picker());
 assert(task.icon===null&&task.terminal_color===null&&refreshes>=2,'reset restores defaults without terminal recreation');
 document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(String(error.stack||error));});
'''
    scripts = ''.join('<script>'+ (static/path).read_text()+'</script>' for path in [
        'js/lib/scope-links.js','js/lib/sidebar-scope-picker.js','js/lib/workspace-objectives.js'])
    css = LAB_SHELL_CSS.read_text() + (static/'css/workspace-objectives.css').read_text()
    html = '<!doctype html><meta charset="utf-8"><style>'+css+'</style><body class="term-open"><div data-objectives-sidebar></div><section id="termPanel" class="term-panel term-sessions-full"><div class="term-stage"><div class="term-session-switcher" id="termSessionSwitcher"><div class="term-sessions" id="termSessionList"></div></div></div></section><script>window.LAB_LINK_SERVICES='+ (static/'link-services.json').read_text()+';'+palette+setup+'</script>'+scripts+'<script>'+_js_between('  function _termTaskStatusLabel(', '  function _termTaskPlaceholderHtml(')+_js_between('  function _termTaskPlaceholderHtml(', '  function termRenderSessionList()')+checks+'</script>'
    _check_project_html(tmp_path, html)
