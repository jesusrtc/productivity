"""Workspace terminal launch choices are deliberate, scoped, and accessible."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

from .test_frontend_terminal_ui import ROOT, _js_between, _run_node
from .test_frontend_project_cache import _check_project_html

STATIC = ROOT / 'core/src/core/static'


def test_default_main_and_task_launches_use_the_resolved_agent():
    callbacks = _js_between('    createWorkflowTerminal:', '    prepareCenter:')
    result = _run_node(r'''
const calls=[],termSpawnSession=(kind,options)=>calls.push({kind,...options});
const currentWorkspace={},_workspaceDisplayName=()=> 'Workflow',_sidebarFileConfigScope='fixture';
const adapter={
''' + callbacks + r'''
};
const launch={id:'objective',name:'Objective',path:'/workspace/objectives/one',context:{path:'/workspace',workspace_id:'work',vault:'fixture'}};
adapter.createWorkflowTerminal(launch);adapter.createTaskTerminal(launch,null);adapter.createTaskTerminal(launch,{id:'task'});
console.log(JSON.stringify(calls));
''')
    assert [call['kind'] for call in result] == ['claude', 'claude', 'claude']
    assert all(call.get('agent') is None for call in result)  # Server resolves workspace/vault defaults.
    assert [call['launchChoice']['scope']['root'] for call in result] == ['/workspace', '/workspace/objectives/one', '/workspace/objectives/one']
    assert result[0]['launchChoice']['association']['main'] == 'workflow'
    assert result[1]['launchChoice']['association']['main'] == 'objective'
    assert result[2]['launchChoice']['association']['task_id'] == 'task'


def test_added_workflow_and_objective_terminals_render_with_existing_mains(tmp_path):
    helpers = _js_between('  async function _termChooseNewScope(', '  async function termKillCurrent(')
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)},tick=()=>new Promise(r=>setTimeout(r,0));
let currentWorkspace={path:'/workspace',is_workspace:true},termSessions=[],termCurrentSession='workflow-main';
const scope={workspace_id:'work',vault:'fixture',path:'/workspace'};
const _termActiveWorkspaceId=()=>scope.workspace_id,_termVaultId=()=>scope.vault,_termHomeSection=()=>null;
const _workspaceDisplayName=()=> 'Workflow',_sidebarFileConfigScope='fixture::work',_sidebarFileConfig={};
const _termSelectedScope=()=>({root:'/unrelated'}),_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionsCache=new Map(),_termInvalidateSessionReads=()=>{},_termClearDead=()=>{};
const termSetStatus=()=>{},termSetAutoSpawnEnabled=async()=>{},_termSaveHomeAssociation=()=>{};
const CEREBRO_WORKSPACE_ID='__cerebro__',SELF_WORKSPACE_ID='__self__',ASSISTANT_WORKSPACE_ID='__assistant__';
const registry={enabled:true,revision:'0',focused:['one','two'],terminal_links:{},objectives:['one','two'].map(id=>({
 id,name:id,path:'/workspace/objectives/'+id,color:'#58a6ff',purpose:'',tasks:[],worktrees:[],resources:[],shared_assets:[],archived_assets:[]}))};
const addMain=(name,association)=>{const s={name,logical_name:name,session_id:'uuid-'+name,cwd:'/workspace'};
 termSessions.push(s);registry.terminal_links[s.session_id]=association;};
addMain('workflow-main',{main:'workflow'});addMain('objective-main',{objective_id:'one',main:'objective'});
const posts=[],actions=[],errors=[];window.alert=message=>{throw Error(message)};
addEventListener('error',e=>errors.push(e.message));addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
window.fetch=async(url,options={})=>{
 if(url==='/api/term/sessions'){
  const body=JSON.parse(options.body);posts.push(body);
  return {ok:true,json:async()=>({name:'added-'+posts.length,logical_name:'added-'+posts.length,
   session_id:'uuid-added-'+posts.length,cwd:body.cwd,linked_scope:body.linked_scope})};
 }
 if(options.method==='POST'){
  const action=JSON.parse(options.body).action;actions.push(action);
  registry.terminal_links[action.session_id]={...action};delete registry.terminal_links[action.session_id].type;
  registry.revision+='!';
 }
 return {ok:true,json:async()=>structuredClone(registry)};
};
function termRenderSessionList(){
 const sessions=LabObjectives.terminalSessions(termSessions);
 document.getElementById('termSessionList').innerHTML=LabObjectives.terminalHtml(sessions,
  t=>`<button class="sess" data-name="${t.name}">${t.name}</button>`,'');
}
const termAttach=name=>{assert(document.querySelector('.sess[data-name="'+name+'"]'),'created tab appears before attachment');termCurrentSession=name;};
const termRefreshSessions=async()=>termRenderSessionList(),termRefreshSessionsByWorkspaceId=termRefreshSessions;
LabObjectives.connect({context:()=>scope,sessions:()=>termSessions,refreshTerminals:termRenderSessionList,
 activateLinkedTerminal:()=>{},prepareCenter:()=>{}});
(async()=>{try{
 await LabObjectives.load();LabObjectives.selectObjective('one',{activateTerminal:false});
 const launch=async index=>{const pending=termSpawnSession('terminal',{startFresh:true});await tick();
  document.querySelector('[data-folder-choice="'+index+'"]').click();await pending;};
 await launch(0);
 assert(posts.length===1,'Add workflow creates a new session even with its main present');
 const workflow=document.querySelector('.sess[data-name="added-1"]');
 assert(workflow&&!workflow.closest('.objective-terminal-group'),'workflow terminal appears above Objective groups');
 await launch(1);await launch(1);
 assert(posts.length===3,'each Add Objective creates an independent session');
 for(const name of ['added-2','added-3'])assert(document.querySelector('.sess[data-name="'+name+'"]')?.closest('.objective-terminal-group').querySelector('[data-select-objective]').dataset.selectObjective==='one','Objective terminal appears in its chosen group with WIP filtering on');
 assert(registry.terminal_links['uuid-workflow-main'].main==='workflow'&&registry.terminal_links['uuid-objective-main'].main==='objective','creation preserves both fixed mains');
 assert(actions[0].view==='workflow'&&actions[1].view==='objective'&&!actions.some(a=>a.main),'ordinary launches persist separate contexts');
 assert(posts[0].cwd==='/workspace'&&posts[1].cwd==='/workspace/objectives/one','chosen folders remain exact');
 LabObjectives.selectObjective('two',{activateTerminal:false});termRenderSessionList();
 assert(document.querySelector('.sess[data-name="added-1"]')&&!document.querySelector('.sess[data-name="added-2"]').closest('.objective-terminal-rows').getClientRects().length,'workflow stays visible and outgoing Objective terminals fold with their own group');
 await LabObjectives.load(undefined,true);LabObjectives.selectObjective('one',{activateTerminal:false});termRenderSessionList();
 assert(document.querySelector('.sess[data-name="added-2"]').getClientRects().length>0&&document.querySelectorAll('[data-name="workflow-main"],[data-name="objective-main"]').length===2,'refresh restores ordinary terminals without replacing main roles');
 assert(!errors.length,'no browser errors: '+errors.join('\n'));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    html = '<!doctype html><meta charset="utf-8"><body class="workspace-active"><main id="content"></main><div id="termSessionList"></div>'
    html += '<script>'+(STATIC / 'js/lib/workspace-objectives.js').read_text()+'</script><script>'+(STATIC / 'js/lib/terminal-folder.js').read_text()+'</script><script>'+helpers+setup+'</script>'
    _check_project_html(tmp_path, html)


def test_current_task_launch_is_recommended_and_captures_one_primary_assignment():
    result = _run_node((STATIC / 'js/lib/terminal-folder.js').read_text() + r'''
const rows=LabTerminalFolder.choices('/workspace','Workflow',{},'one::work',{
 id:'objective',name:'Objective',path:'/workspace/objectives/one',context:{workspace_id:'work',vault:'one',path:'/workspace'},
 task_terminals:true,task:{id:'task',title:'Verify the fix'},worktrees:[]});
console.log(JSON.stringify(rows));
'''.replace('LabTerminalFolder.choices', 'window.LabTerminalFolder.choices'))
    assert [row['kind'] for row in result] == ['Task', 'Workflow', 'Objective', 'Worktree']
    assert result[0]['name'] == 'Current task (recommended)'
    assert result[0]['association']['task_id'] == 'task'
    assert result[0]['association']['rename_to_task'] is True
    assert result[0]['scope']['root'] == '/workspace/objectives/one'


def test_choices_include_workspace_and_exact_pins_only():
    result = _run_node((STATIC / 'js/lib/terminal-folder.js').read_text() + r'''
const config={folderScopes:[{path:'/repo',label:'Project',color:'#123abc'},
 {path:'/trees/feature',projectPath:'/repo',kind:'worktree',label:'Project/feature',color:'#456def'},
 {path:'/unused',label:'Unused'}],pinnedScopes:['/repo','/trees/feature','/workspace','/repo'],
 selectedFolders:{'/workspace':'/unused'},selectedWorktrees:{'/unused':'/unpinned-tree'}};
console.log(JSON.stringify(window.LabTerminalFolder.choices('/workspace','Workspace',config,'vault::work')));
''')
    assert [row['scope']['root'] for row in result] == ['/workspace', '/repo', '/trees/feature']
    assert [row['kind'] for row in result] == ['Workspace', 'Folder', 'Worktree']
    assert result[2]['scope']['project_root'] == '/repo'
    assert result[2]['scope']['worktree'] == '/trees/feature'
    assert all(row['scope']['base_root'] == '/workspace' and row['scope']['config_scope'] == 'vault::work'
               for row in result)


def test_objective_launch_context_captures_owned_worktrees_and_exact_associations():
    source = (STATIC / 'js/lib/workspace-objectives.js').read_text()
    helpers = source[source.index('  function terminalLaunchContext('):source.index('  function tree(')]
    result = _run_node((STATIC / 'js/lib/terminal-folder.js').read_text() + r'''
const origin={workspace_id:'work',vault:'one',path:'/workspace'};
const o={id:'one',name:'Current objective',path:'/workspace/objectives/one',worktrees:[
 {id:'root',path:'/workspace'},{id:'self',path:'/workspace/objectives/one'},
 {id:'feature',path:'/trees/feature',resolved_path:'/real/feature',repo:'/repo',kind:'worktree',label:'Feature',color:'#58a6ff'},
 {id:'folder',path:'/project',repo:'/project',kind:'folder',label:'Project'}]};
const context=()=>origin,objective=()=>o,active=()=>true,focusedTask=()=>null,taskTerminalsEnabled=()=>false;
const mutations=[],change=(action,options)=>mutations.push({action,...options}),terminalIdentity=t=>t.session_id;
''' + helpers + r'''
const launch=terminalLaunchContext();
const choices=window.LabTerminalFolder.choices('/workspace','Workflow',{
 pinnedScopes:['/other-objective'],folderScopes:[{path:'/other-objective',kind:'worktree'}]},'one::work',launch);
const workflow=choices[0],objectiveChoice=choices[1],worktree=choices[2].children[0];
associateNewTerminal({session_id:'objective-terminal'},objectiveChoice.association);
associateNewTerminal({session_id:'worktree-terminal'},worktree.association);
origin.vault='different';o.worktrees[2].path='/moved';
console.log(JSON.stringify({launch,workflow,objectiveChoice,worktrees:choices[2].children,mutations}));
''')
    assert [row['scope']['root'] for row in result['worktrees']] == ['/trees/feature', '/project']
    assert result['workflow']['scope']['root'] == '/workspace'
    assert result['workflow']['association'] == {'context': result['launch']['context'], 'view': 'workflow'}
    assert result['objectiveChoice']['scope']['root'] == '/workspace/objectives/one'
    assert result['worktrees'][0]['scope']['worktree'] == '/trees/feature'
    assert result['worktrees'][0]['scope']['project_root'] == '/repo'
    assert result['worktrees'][1]['scope']['worktree'] is None
    assert result['launch']['context']['vault'] == 'one'
    assert result['mutations'] == [
        {'action': {'type': 'terminal', 'session_id': 'objective-terminal', 'objective_id': 'one', 'view': 'objective'},
         'scope': {'workspace_id': 'work', 'vault': 'one', 'path': '/workspace'}},
        {'action': {'type': 'terminal', 'session_id': 'worktree-terminal', 'objective_id': 'one',
                    'folder': {'root': '/trees/feature', 'path': '.'}},
         'scope': {'workspace_id': 'work', 'vault': 'one', 'path': '/workspace'}},
    ]


@pytest.mark.parametrize('viewport', [1440, 390])
def test_folder_chooser_browser(tmp_path, viewport):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node required')
    setup = r'''
const assert=(condition,message)=>{if(!condition)throw Error(message)};
let workspace='work',vault='one',home=null;
const _termActiveWorkspaceId=()=>workspace,_termVaultId=()=>vault,_termHomeSection=()=>home;
const _workspaceDisplayName=()=> 'My workspace';
let currentWorkspace={path:'/workspace',is_workspace:true};
let _sidebarFileConfigScope='one::work';
const _sidebarFileConfig={folderScopes:[{path:'/repo',label:'Project',color:'#58a6ff'},
 {path:'/trees/feature',label:'Project/feature',kind:'worktree',projectPath:'/repo',color:'#d2a8ff'},
 {path:'/unused',label:'Unused'}],pinnedScopes:['/repo','/trees/feature']};
let termSessions=[],posts=[],attachments=[],associations=[],alerts=[],launchObjective=null,associationFailure=false;
window.alert=message=>alerts.push(message);
window.LabObjectives={load:async()=>{},terminalLaunchContext:()=>launchObjective,
 associateNewTerminal:async(terminal,association)=>{associations.push({terminal,association});
  if(associationFailure)throw Error('Save failed');}};
const _termSelectedScope=()=>({root:'/unused'});
const termSetStatus=()=>{},termSetAutoSpawnEnabled=async()=>{},_termClearDead=()=>{};
const _termSessionsKey=(w,v)=>v+'::'+w,_termInvalidateSessionReads=()=>{};
const _termSessionsCache=new Map();
const _termSaveHomeAssociation=()=>{};
const termAttach=(name,w)=>attachments.push({name,w});
const termRefreshSessions=async()=>{},termRefreshSessionsByWorkspaceId=async()=>{};
const termRenderSessionList=()=>{};
const CEREBRO_WORKSPACE_ID='__cerebro__',SELF_WORKSPACE_ID='__self__',ASSISTANT_WORKSPACE_ID='__assistant__';
window.fetch=async(url,options)=>{const body=JSON.parse(options.body);posts.push(body);
 return {ok:true,json:async()=>({name:'new'+posts.length,logical_name:'new'+posts.length,
  cwd:body.cwd,linked_scope:body.linked_scope})};};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const q=selector=>document.querySelector(selector);
const pick=i=>q(`[data-folder-choice="${i}"]`).click();
const cancelChoice=()=>q('.term-folder-footer [data-cancel]').click();
const open=()=>termSpawnSession('terminal',{startFresh:true});
'''
    helpers = _js_between('  async function _termChooseNewScope(', '  async function termKillCurrent(')
    checks = r'''
(async()=>{
 document.getElementById('new').focus();
 let pending=open();await tick();
 assert(!posts.length&&!attachments.length,'nothing starts before a choice');
 assert(q('[role=dialog]')&&q('#termFolderHint').textContent.includes('stays fixed'),'dialog announces fixed folder');
 assert(q('.term-folder-list').children.length===3,'workspace and pinned choices only');
 assert(document.activeElement===q('[data-folder-choice="0"]'),'initial keyboard focus is in chooser');
 assert(!q('[aria-selected=true]'),'no remembered selection');
 const dialog=q('[role=dialog]'),rect=dialog.getBoundingClientRect();
 assert(rect.left>=0&&rect.right<=innerWidth+1&&dialog.scrollWidth<=dialog.clientWidth+1,'dialog fits viewport');
 pick(2);await pending;
 assert(posts[0].cwd==='/trees/feature'&&posts[0].linked_scope.worktree==='/trees/feature','worktree chosen as exact launch folder');
 assert(document.activeElement===document.getElementById('new'),'focus returns to launch control');
 pending=open();await tick();cancelChoice();await pending;assert(posts.length===1,'cancel creates no session');
 pending=open();await tick();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 await pending;assert(posts.length===1&&!q('.term-folder-overlay'),'escape cancels');
 pending=open();await tick();
 q('.term-folder-footer button').focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));
 assert(document.activeElement===q('.fm-close'),'focus stays inside chooser');
 pick(0);await pending;assert(posts[1].cwd==='/workspace','workspace choice ignores selected sidebar folder');
 pending=open();await tick();vault='two';
 await pending;assert(posts.length===2&&!q('.term-folder-overlay'),'navigation cancels captured origin');
 vault='one';pending=open();await tick();
 // A second launch cancels the previous request without creating two terminals.
 const replacement=open();await tick();await pending;
 pick(1);await replacement;assert(posts.length===3&&posts[2].cwd==='/repo','each launch asks independently');
 _sidebarFileConfig.pinnedScopes=[];
 pending=open();await tick();assert(q('.term-folder-list').children.length===1,'even workspace-only launch asks');
 cancelChoice();await pending;
 // File-created terminals must ask too, and cannot silently use the file folder.
 _sidebarFileConfig.pinnedScopes=['/repo','/trees/feature'];
 pending=termSpawnSession('claude',{startFresh:true,agent:'codex',linkedScope:{root:'/file-folder'}});
 await tick();pick(1);await pending;assert(posts[3].cwd==='/repo'&&posts[3].agent==='codex','file launch uses explicit choice');
 launchObjective={id:'objective-one',name:'Objective one',path:'/workspace/objectives/one',
  context:{workspace_id:'work',vault:'one',path:'/workspace'},worktrees:[
   {id:'own',path:'/trees/own',repo:'/project',label:'Owned worktree',kind:'worktree',color:'#58a6ff'},
   {id:'another',path:'/trees/another',repo:'/project',label:'Another worktree',kind:'worktree',color:'#d2a8ff'}]};
 const originalObjective=launchObjective;
 pending=open();await tick();
 assert([...q('.term-folder-list').querySelectorAll('strong')].map(n=>n.textContent).join('|')==='Current workflow|Current Objective|Specific worktree','three launch categories');
 const launchDialog=q('[role=dialog]'),launchRect=launchDialog.getBoundingClientRect();
 assert(launchRect.left>=0&&launchRect.right<=innerWidth+1&&launchDialog.scrollWidth<=launchDialog.clientWidth+1,'Objective chooser fits viewport');
 pick(0);await pending;assert(posts.at(-1).cwd==='/workspace'&&associations.at(-1).association.view==='workflow'&&!associations.at(-1).association.objective_id,'workflow terminal stays at its root without an Objective association');
 pending=open();await tick();pick(1);await pending;
 assert(posts.at(-1).cwd==='/workspace/objectives/one'&&associations.at(-1).association.objective_id==='objective-one'&&!associations.at(-1).association.folder,'Objective launch saves a whole-Objective assignment');
 pending=open();await tick();const before=posts.length;pick(2);
 assert(posts.length===before&&q('.term-folder-list h3').textContent.includes('Objective one'),'worktree category asks before starting');
 assert([...q('.term-folder-list').querySelectorAll('small')].some(n=>n.textContent==='/trees/own')&&!q('.term-folder-list').textContent.includes('/repo'),'only current Objective worktrees are offered, not unrelated pins');
 assert(document.activeElement===q('[data-folder-choice="0"]'),'worktree list receives keyboard focus');
 q('[data-folder-back]').click();assert(q('[data-folder-choice="2"]')===document.activeElement,'back returns to worktree category');
 pick(2);pick(1);await pending;
 assert(posts.at(-1).cwd==='/trees/another'&&posts.at(-1).linked_scope.project_root==='/project'&&associations.at(-1).association.folder.root==='/trees/another','chosen worktree launch and association use exact checkout');
 pending=open();await tick();launchObjective={...launchObjective,id:'different'};
 await pending;assert(posts.length===before+1&&!q('.term-folder-overlay'),'Objective navigation cancels creation');
 pending=open();await tick();launchObjective={...launchObjective,worktrees:[]};
 await pending;assert(posts.length===before+1,'changed worktree list cancels stale choices');
 pending=open();await tick();assert(q('[data-folder-choice="2"]').disabled,'no-worktree Objective still permits workflow or Objective');
 associationFailure=true;pick(1);await pending;
 assert(attachments.at(-1).name==='new'+posts.length&&alerts.at(-1).includes('Terminal created, but'),'association failure preserves and opens the created session');
 associationFailure=false;launchObjective=null;
 document.body.classList.remove('workspace-active');
 pending=open();await pending;assert(posts.at(-1).cwd==='/unused','other terminal surfaces keep their launch behavior');
 document.body.classList.add('workspace-active');
 launchObjective=originalObjective;
 open();await tick();
 document.getElementById('result').textContent='PASS choices, explicit launch, cancel, keyboard, navigation, repeated launch, agents, mobile';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    page = tmp_path / 'folder.html'
    css = (STATIC / 'css/lab-shell.css').read_text() + (STATIC / 'css/terminal-folder.css').read_text()
    page.write_text('<!doctype html><meta charset="utf-8"><style>' + css + '</style>'
                    '<body class="workspace-active"><button id="new">New terminal</button><pre id="result">PENDING</pre>'
                    '<script>' + setup + '</script><script>' + (STATIC / 'js/lib/terminal-folder.js').read_text()
                    + '</script><script>' + helpers + checks + '</script>')
    profile = tmp_path / 'chrome-profile'
    process = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
                                '--no-default-browser-check', '--allow-file-access-from-files',
                                '--user-data-dir=' + str(profile), '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        driver = tmp_path / 'browser.mjs'
        driver.write_text((ROOT / 'scripts/chrome-dump-auth.mjs').read_text()
                          .replace('width: 1440,', 'width: ' + str(viewport) + ','))
        result = subprocess.run([node, str(driver), str(profile), page.as_uri(), str(tmp_path / 'dom.html'),
                                 str(tmp_path / 'folder.png')], capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''})
        assert result.returncode == 0, result.stderr
        html = (tmp_path / 'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
    assert result and result[1].startswith('PASS '), result[1] if result else html[-1500:]
