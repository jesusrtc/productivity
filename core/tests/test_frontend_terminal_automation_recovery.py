"""Manual recovery, nested child selection and copy-only launch guidelines."""
import json

from .test_frontend_terminal_ui import _run_node, _js_between, LAB_APP, LAB_SHELL_CSS
from .test_frontend_project_cache import _check_project_html

PLUGIN = (LAB_APP.parent / 'lib/terminal-automations.js').read_text()


def test_recovery_targets_only_stopped_descendants_and_keeps_captured_scope():
    result = _run_node(r'''
let release,requests=[];
global.fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});await new Promise(r=>release=r);return{ok:true,json:async()=>({sessions:[]})}};
''' + PLUGIN + r'''
const parent={logical_name:'parent'},rows=[parent,
 {logical_name:'child',automation:{can_relaunch:true,launch_id:'child-run'}},
 {logical_name:'nested',automation:{can_relaunch:true,launch_id:'nested-run'}},
 {logical_name:'live',automation:{can_relaunch:false,launch_id:'live-run'}},
 {logical_name:'other',automation:{can_relaunch:true,launch_id:'other-run'}}];
const parents={child:'parent',nested:'child',live:'parent'};
(async()=>{
 const targets=LabTerminalAutomations.recoveryTargets(parent,rows,parents);
 const scope={id:'demo',vault:'one'};
 const pending=LabTerminalAutomations.relaunch(scope,targets);
 let duplicate='';try{await LabTerminalAutomations.relaunch(scope,targets)}catch(error){duplicate=error.message}
 scope.id='other';release();await pending;
 console.log(JSON.stringify({targets,requests,duplicate}));
})();
'''.replace('LabTerminalAutomations.', 'window.LabTerminalAutomations.'))
    assert [row['logical_name'] for row in result['targets']] == ['child', 'nested']
    assert len(result['requests']) == 1
    assert result['requests'][0]['body']['workspace_id'] == 'demo'
    assert result['requests'][0]['body']['vault'] == 'one'
    assert result['duplicate']


def test_large_parent_recovery_batches_all_children_in_original_scope():
    result = _run_node(r'''
let requests=[],scope={id:'demo',vault:'one'};
global.fetch=async(url,options)=>{const body=JSON.parse(options.body);requests.push(body);scope.id='other';return{ok:true,json:async()=>({sessions:body.targets,skipped:[],errors:[]})}};
''' + PLUGIN + r'''
(async()=>{
 const targets=Array.from({length:205},(_,i)=>({logical_name:'child-'+i,launch_id:'run-'+i}));
 const result=await window.LabTerminalAutomations.relaunch(scope,targets);
 console.log(JSON.stringify({requests,count:result.sessions.length}));
})();
''')
    assert [len(row['targets']) for row in result['requests']] == [100, 100, 5]
    assert result['count'] == 205
    assert all(row['workspace_id'] == 'demo' and row['vault'] == 'one' for row in result['requests'])
    assert len({row['request_id'] for row in result['requests']}) == 1


def test_native_white_markers_recovery_buttons_and_guidelines_never_execute(tmp_path):
    pill = _js_between('  function _termTaskStatusLabel(', '  function _termMarkVisibleCompletionSeen(')
    setup = r'''
const assert=(value,label)=>{if(!value)throw Error(label)};
const termSessEsc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _termActiveWorkspaceId=()=> 'demo',_termRecentScopeKey=()=> 'demo';
let termCurrentWorkspaceId='demo',termCurrentSession='running';
const _termSessionDisplay=s=>s.label||s.logical_name;
const _termSessionVisual=()=>({kind:'terminal',badge:'Terminal',icon:'▣'}),_termSessionRecentMeta=()=>null,_termSessionIsWorking=()=>false;
const _termSessionContext=()=>({label:'Requests'}),_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}',_termSessionAssociationHtml=()=>'';
const termDeadSessions=new Set(),_termReadGroupState=()=>({}),_termSubtabParents=()=>({[stopped.logical_name]:'parent',[running.logical_name]:'parent',[unknown.logical_name]:'parent'});
const guides=[{title:'With debugger',text:'  python -m debugpy app.py\n# literal <script> $(do-not-run)\n\n'},{title:'Without debugger',text:'python app.py'}];
const parent={name:'parent',logical_name:'parent',label:'Parent'};
const stopped={name:'stopped',logical_name:'automation-'+ 'a'.repeat(32)+'-1',label:'Stopped',automation:{can_relaunch:true,launch_id:'stopped-run',reason:'SSH disconnected',guidelines:guides}};
const running={name:'running',logical_name:'automation-'+ 'a'.repeat(32)+'-2',label:'Running',automation:{can_relaunch:false,launch_id:'running-run',reason:'Running'}};
const unknown={name:'unknown',logical_name:'automation-'+ 'a'.repeat(32)+'-3',label:'Unknown',automation:{can_relaunch:false,launch_id:'unknown-run',reason:'Status unavailable'}};
const termSessions=[parent,stopped,running,unknown];
let copied=[],calls=[];
Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>copied.push(text)}});
window.fetch=async(url,options)=>{calls.push(url);return{ok:true,json:async()=>({sessions:[]})}};
window.LabObjectives={terminalMain:()=>null,taskForTerminal:()=>null};
'''
    checks = r'''
(async()=>{
 const list=document.getElementById('termSessionList'),switcher=document.getElementById('termSessionSwitcher');
 list.innerHTML=termSessions.map(_termSessionPillHtml).join('');
 const row=name=>list.querySelector('[data-name="'+name+'"]');
 assert(row('stopped').querySelector('[data-automation-relaunch]'),'stopped SSH gets recovery');
 assert(row('parent').querySelector('[data-automation-relaunch]').title.includes('1 stopped child'),'parent recovers only stopped child');
 assert(!row('running').querySelector('[data-automation-relaunch]')&&!row('unknown').querySelector('[data-automation-relaunch]'),'running and unknown hidden');
 for(const name of ['stopped','running','unknown']){
  assert(getComputedStyle(row(name),'::before').display==='block','folded bullet visible');
  assert(getComputedStyle(row(name),'::before').backgroundColor==='rgb(230, 237, 243)','folded bullet white');
  assert(getComputedStyle(row(name).querySelector('.sess-label')).display==='none','folded name hidden');
 }
 switcher.classList.add('term-tabs-open');
 assert(getComputedStyle(row('stopped'),'::before').display==='none','expanded marker hidden');
 assert(getComputedStyle(row('stopped').querySelector('.sess-label')).display==='block','expanded name visible');
 const host=document.getElementById('guidelines');LabTerminalAutomations.renderGuidelines(host,stopped);
 assert(!host.hidden&&host.querySelectorAll('pre').length===2,'guidelines visible');
 host.querySelector('button').click();await Promise.resolve();await Promise.resolve();
 assert(copied[0]===guides[0].text&&!calls.length,'copy exact text without execution or launch requests');
 host.querySelector('details').open=false;LabTerminalAutomations.renderGuidelines(host,{...stopped,automation:{...stopped.automation,reason:'changed'}});
 assert(!host.querySelector('details').open,'poll preserves guideline collapse');
 LabTerminalAutomations.renderGuidelines(host,running);assert(host.hidden,'different terminal clears guidelines');
 const editor=document.getElementById('editor');const read=LabTerminalAutomations.editor(editor,[{id:'remote',name:'Remote',steps:[{label:'SSH',command:'ssh example',cwd:'',guidelines:guides}]}],()=>{});
 assert(JSON.stringify(read()[0].steps[0].guidelines)===JSON.stringify(guides),'saved multiline guidelines roundtrip');
 editor.querySelector('[data-add-guide]').click();const guide=editor.querySelectorAll('[data-guide]')[2];guide.querySelector('[data-guide-title]').value='Logs';guide.querySelector('[data-guide-text]').value='tail -f app.log';
 assert(read()[0].steps[0].guidelines.length===3,'add optional guideline');guide.querySelector('[data-remove-guide]').click();assert(read()[0].steps[0].guidelines.length===2,'remove optional guideline');
 assert(!calls.length,'editing guidelines never launches commands');
 document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(String(error.stack||error))});
'''.replace('LabTerminalAutomations.', 'window.LabTerminalAutomations.')
    html = '<!doctype html><style>'+LAB_SHELL_CSS.read_text()+'</style><body class="term-open"><section class="term-panel term-sessions-full"><div class="term-stage"><div class="term-session-switcher" id="termSessionSwitcher"><div class="term-sessions" id="termSessionList"></div></div></div></section><div id="guidelines"></div><div id="editor"></div><script>'+setup+PLUGIN+pill+checks+'</script>'
    _check_project_html(tmp_path, html)
