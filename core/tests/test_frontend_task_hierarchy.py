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
 'uuid-grand':{objective_id:'one',task_id:'grand'},'uuid-independent':{objective_id:'one',task_id:'independent'},
 'uuid-extra':{objective_id:'one',task_id:'child',primary:false}}};
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
    assert result['initial']['taskTerminals']['one/child'] == ['child', 'objective-terminal:one:child']
    assert result['moved']['tabParents'] == {'extra':'child', 'unrelated':'independent'}
    assert result['moved']['tabRoots'] == []
    assert result['moved']['tabAfter'] == {'child':'independent'}
    assert result['moved']['tabDisplayMains'] == {}
    assert result['restored'] == result['moved'] and result['unchanged']



def test_task_sibling_reorder_preserves_member_order_and_legacy_preferences():
    result = _run_node(r'''
const _TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'fixture',_termSessionsKey=(w,v)=>v+'::'+w;
let stored='{}';const localStorage={getItem:()=>stored,setItem:(key,value)=>stored=value};
const termSessions=['a','a2','b'].map(name=>({name,logical_name:name,session_id:name}));
const data={objectives:[{id:'one',tasks:[{id:'a'},{id:'b'}]}],terminal_links:{a:{objective_id:'one',task_id:'a'},b:{objective_id:'one',task_id:'b'}}};
''' + GROUPS + r'''
_termWriteGroupState(_termNormalizeGroupState({taskHierarchy:{'one/a':'["a:0"]','one/b':'["b:1"]'},tabAfter:{a:'a2'},tabParents:{a2:'a'}}));
_termSyncTaskHierarchy(data);const migrated=_termReadGroupState();
data.objectives[0].tasks.reverse();_termSyncTaskHierarchy(data);const reordered=_termReadGroupState();
console.log(JSON.stringify({migrated,reordered}));
''')
    assert result['migrated']['tabAfter'] == result['reordered']['tabAfter'] == {'a':'a2'}
    assert result['migrated']['tabParents'] == result['reordered']['tabParents'] == {'a2':'a'}
    assert result['reordered']['taskHierarchy'] == {'one/a':'["a"]', 'one/b':'["b"]'}
