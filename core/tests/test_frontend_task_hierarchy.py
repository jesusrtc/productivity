"""Moving a task overrides stale layout without changing session identity."""
from .test_frontend_terminal_ui import _run_node, _js_between
from .test_frontend_terminal_subtabs import OBJECTIVES


GROUPS = _js_between('  function _termGroupScopeKey()', '  function _termSessionDisplay(s)')


def test_task_hierarchy_changes_clear_only_affected_primary_layout_and_survive_reload():
    result = _run_node(r'''
const _TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'fixture',_termSessionsKey=(w,v)=>v+'::'+w;
let stored='{}';const localStorage={getItem:()=>stored,setItem:(key,value)=>stored=value};
const termSessions=['parent','child','grand','extra','independent','unrelated'].map(name=>({name,logical_name:name,session_id:'uuid-'+name,cwd:'/fixed/'+name}));
const task=(id,children=[])=>({id,children});
const data={objectives:[{id:'one',tasks:[task('parent',[task('child',[task('grand')])]),task('independent')]}],terminal_links:{
 'uuid-parent':{objective_id:'one',task_id:'parent'},'uuid-child':{objective_id:'one',task_id:'child'},
 'uuid-grand':{objective_id:'one',task_id:'grand'},'uuid-independent':{objective_id:'one',task_id:'independent'}}};
''' + GROUPS + r'''
_termWriteGroupState(_termNormalizeGroupState({tabParents:{child:'independent',extra:'child',unrelated:'independent'},tabRoots:['grand'],tabAfter:{child:'independent'},tabDisplayMains:{independent:'child'}}));
_termSyncTaskHierarchy(data);const initial=_termReadGroupState();
const moving=data.objectives[0].tasks[0].children.pop();data.objectives[0].tasks.push(moving);
const before=JSON.stringify(termSessions);_termSyncTaskHierarchy(data);
const moved=_termReadGroupState();_termSyncTaskHierarchy(JSON.parse(JSON.stringify(data)));
const restored=_termReadGroupState();
console.log(JSON.stringify({initial,moved,restored,unchanged:before===JSON.stringify(termSessions)}));
''')
    assert result['initial']['tabParents']['child'] == 'independent'
    assert result['moved']['tabParents'] == {'extra':'child', 'unrelated':'independent'}
    assert result['moved']['tabRoots'] == []
    assert result['moved']['tabAfter'] == {} and result['moved']['tabDisplayMains'] == {}
    assert result['restored'] == result['moved'] and result['unchanged']


def test_primary_terminal_drop_moves_task_while_unowned_children_keep_manual_layout():
    source = OBJECTIVES.read_text()
    move = source[source.index('  async function moveForTerminalDrop('):source.index('  function associate(row)')]
    result = _run_node(r'''
const parent={id:'parent',children:[]},sibling={id:'sibling',children:[]},sourceTask={id:'source',children:[]};
const o={id:'one',tasks:[parent,sourceTask,sibling]};
const tasks=o=>o.tasks.flatMap(t=>[t,...t.children]),taskParent=(task,o)=>tasks(o).find(t=>t.children.includes(task))||null;
const context=()=>({workspace_id:'demo'}),key=s=>s.workspace_id,active=()=>true;
const bindings=new Map([['source',{objective:o,task:sourceTask,inherited:false}],['target',{objective:o,task:parent,inherited:false}],['extra',{objective:o,task:parent,inherited:true}]]);
const terminalTask=s=>bindings.get(s?.logical_name),bridge={refreshTerminals(){}},actions=[];
async function change(action){
 actions.push(action);const currentParent=taskParent(sourceTask,o),old=currentParent?currentParent.children:o.tasks;old.splice(old.indexOf(sourceTask),1);
 const newParent=tasks(o).find(t=>t.id===action.parent_id),rows=newParent?newParent.children:o.tasks;
 const anchor=rows.findIndex(t=>t.id===action.before_id);rows.splice(anchor<0?rows.length:anchor,0,sourceTask);
}
''' + move + r'''
(async()=>{
 const source={logical_name:'source'},target={logical_name:'target'},extra={logical_name:'extra'};
 const moved=await moveForTerminalDrop(source,target,{relation:'child'}),nested=parent.children[0]?.id;
 const promoted=await moveForTerminalDrop(source,null),root=o.tasks.at(-1)?.id;
 const manual=await moveForTerminalDrop(extra,target,{relation:'child'});
 await moveForTerminalDrop(source,target,{relation:'below',placeBefore:true});
 console.log(JSON.stringify({moved,nested,promoted,root,manual,actions}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['moved'] and result['nested'] == 'source'
    assert result['promoted'] and result['root'] == 'source'
    assert result['manual'] is False and len(result['actions']) == 3
    assert result['actions'][0]['parent_id'] == 'parent'
    assert result['actions'][1]['parent_id'] is None
    assert result['actions'][2]['before_id'] == 'parent'


def test_terminal_reorder_uses_task_move_before_writing_manual_parent_overrides():
    reorder = _js_between('  async function termReorderItems(', '  function termReorderSessions(')
    result = _run_node(r'''
const sessions=['source','target'].map(name=>({name,logical_name:name,session_id:'uuid-'+name}));
let termSessions=sessions,_termReorderPending=false,stored=0;
const _termReadGroupState=()=>({}),_termPlanItemMove=()=>({order:['s:target','s:source']}),_termWriteGroupState=()=>stored++;
const termRenderSessionList=()=>{},_termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'fixture',explorerToast=()=>{},setTimeout=()=>{};
const calls=[];
window.LabObjectives={moveForTerminalDrop:async(...args)=>{calls.push(args);return true;}};
''' + reorder + r'''
(async()=>{const before=JSON.stringify(termSessions),moved=await termReorderItems('s:source','s:target',false,undefined,'child');
console.log(JSON.stringify({moved,stored,calls,unchanged:before===JSON.stringify(termSessions)}));})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['moved'] and result['unchanged'] and result['stored'] == 0
    assert result['calls'][0][0]['session_id'] == 'uuid-source'
    assert result['calls'][0][1]['session_id'] == 'uuid-target'
    assert result['calls'][0][2] == {'relation':'child', 'placeBefore':False}
