"""Active/pinned scope navigation, usage ranking, and terminal association."""
from .test_frontend_terminal_ui import ROOT, _js_between, _run_node


def helpers():
    return """
const stored = {}, localStorage = {getItem:key=>stored[key]||null,setItem:(key,value)=>stored[key]=value};
const currentRepo = null, currentWorkspace = {path:'/workspace',repos:[]};
const document = {body:{classList:{contains:()=>false}},addEventListener(){},querySelector:()=>null};
const window = {}, esc = String, escAttr = String;
""" + _js_between('  let showDotFiles = false;', '  function filterDotFiles(nodes)')


def test_only_active_and_pinned_scopes_are_visible_and_pins_survive_reload():
    result = _run_node(helpers() + """
_sidebarFileConfig = _sidebarNormalizeFileConfig({folderScopes:[
  {path:'/src/one',label:'One'},{path:'/trees/two',label:'Two/feature',kind:'worktree',projectPath:'/src/two',branch:'feature'},
  {path:'/src/unused',label:'Unused'}], selectedFolders:{'/workspace':'/src/one'}});
const before = _sidebarVisibleScopes('/workspace').map(row=>row.path);
sidebarPinScope({getAttribute:()=>'/src/one'});
_sidebarFileConfig.selectedFolders['/workspace']='/trees/two';
_storeSidebarFileConfig();
_sidebarFileConfig=_loadSidebarFileConfig();
const after = _sidebarVisibleScopes('/workspace').map(row=>row.path);
const html = _sidebarFileScopeButtonsHtml('/workspace');
const direct = [_sidebarScopedRoot('/workspace'),_sidebarActiveWorktreeFolder('/workspace')];
sidebarPinScope({getAttribute:()=>'/src/one'});
const unpinned = _sidebarVisibleScopes('/workspace').map(row=>row.path);
process.stdout.write(JSON.stringify({before,after,unpinned,direct,add:html.includes('sidebar-scope-add'),label:html.includes('Two/feature')}));
""")
    assert result == {'before': ['/src/one'], 'after': ['/src/one', '/trees/two'],
                      'unpinned': ['/trees/two'], 'direct': ['/trees/two', ''], 'add': True, 'label': True}


def test_automatic_colors_use_each_available_color_before_reusing_and_preserve_choices():
    result = _run_node(helpers() + """
for(let i=0;i<20;i++) _sidebarRememberScope({path:'/scope/'+i});
const colors = _sidebarFileConfig.folderScopes.map(row=>row.color);
const reused = _sidebarRememberScope({path:'/scope/21'}).color;
_sidebarFileConfig.folderScopes[0].color='#123456';
_sidebarRememberScope({path:'/scope/0'});
process.stdout.write(JSON.stringify({colors,reused,custom:_sidebarFileConfig.folderScopes[0].color,next:_sidebarNextScopeColor()}));
""")
    assert len(result['colors']) == len(set(result['colors'])) == 20
    assert result['reused'] in result['colors']
    assert result['custom'] == '#123456'


def test_terminal_attachment_pins_exact_worktree_without_repinning_manual_unpin():
    result = _run_node(helpers() + """
const scope = {base_root:'/workspace',project_root:'/src/project',root:'/trees/feature',
  worktree:'/trees/feature',label:'project · feature',config_scope:_sidebarFileConfigScope};
_sidebarPinTerminalScope(scope,'terminal');
const first = _loadSidebarFileConfig();
sidebarPinScope({getAttribute:()=>scope.root});
_sidebarPinTerminalScope(scope,'terminal');
const afterRefresh = [..._sidebarFileConfig.pinnedScopes];
_sidebarPinTerminalScope(scope,'terminal',true);
const reattached = [..._sidebarFileConfig.pinnedScopes];
_sidebarPinTerminalScope({...scope,root:'/elsewhere',config_scope:'another-workspace'},'other',true);
process.stdout.write(JSON.stringify({first,afterRefresh,reattached,paths:_sidebarFileConfig.folderScopes.map(row=>row.path)}));
""")
    assert result['first']['pinnedScopes'] == ['/trees/feature']
    assert result['first']['folderScopes'][0]['label'] == 'project/feature'
    assert result['first']['folderScopes'][0]['kind'] == 'worktree'
    assert result['afterRefresh'] == []
    assert result['reattached'] == ['/trees/feature']
    assert result['paths'] == ['/trees/feature']


def test_terminal_pin_preserves_actual_branch_and_parent_folder_kind():
    result = _run_node(helpers() + """
_sidebarRememberScope({path:'/trees/checkout',label:'project/feature/search',kind:'worktree',projectPath:'/src/project',branch:'feature/search'});
_sidebarRememberScope({path:'/src',label:'Projects',kind:'parent'});
_sidebarPinTerminalScope({base_root:'/workspace',project_root:'/src/project',root:'/trees/checkout',
  worktree:'/trees/checkout',label:'project · feature/search',config_scope:_sidebarFileConfigScope},'one');
_sidebarPinTerminalScope({base_root:'/workspace',project_root:'/src',root:'/src',label:'Projects',config_scope:_sidebarFileConfigScope},'two');
const pinnedBranch=_sidebarFolderScope('/trees/checkout').branch;
_sidebarRememberScope({path:'/trees/checkout',label:'project/feature/new',kind:'worktree',projectPath:'/src/project',branch:'feature/new'});
process.stdout.write(JSON.stringify({pinnedBranch,tree:_sidebarFolderScope('/trees/checkout'),parent:_sidebarFolderScope('/src').kind}));
""")
    assert result['tree']['label'] == 'project/feature/new'
    assert result['tree']['branch'] == 'feature/new'
    assert result['pinnedBranch'] == 'feature/search'
    assert result['parent'] == 'parent'


def test_picker_filters_branches_and_paths_and_sorts_by_usage():
    module = (ROOT / 'core/src/core/static/js/lib/sidebar-scope-picker.js').read_text()
    result = _run_node('const window = {};\n' + module + """
const rows=[{path:'/src/z',label:'Z'},{path:'/src/a',label:'A'},
  {path:'/trees/search',label:'Project/feature/search',branch:'feature/search',kind:'worktree'}];
const usage={'/src/z':{count:4,lastUsed:1},'/src/a':{count:1,lastUsed:100}};
process.stdout.write(JSON.stringify({sorted:window.LabSidebarScopes.ranked(rows,usage).map(row=>row.path),
  branch:window.LabSidebarScopes.ranked(rows,usage,'feature search').map(row=>row.path),
  path:window.LabSidebarScopes.ranked(rows,usage,'/src/a').map(row=>row.path),
  empty:window.LabSidebarScopes.ranked(rows,usage,'missing')}));
""")
    assert result == {'sorted': ['/src/z', '/src/a', '/trees/search'], 'branch': ['/trees/search'],
                      'path': ['/src/a'], 'empty': []}


def test_picker_keywords_filter_scope_kind_and_combine_with_text():
    module = (ROOT / 'core/src/core/static/js/lib/sidebar-scope-picker.js').read_text()
    result = _run_node('const window = {};\n' + module + """
const rows=[
  {path:'/src/project',label:'Project',kind:'folder',branch:'feature'},
  {path:'/src/branch-tools',label:'Branch tools',kind:'folder'},
  {path:'/src',label:'Projects',kind:'parent'},
  {path:'/trees/search',label:'Project/feature/search',branch:'feature/search',kind:'worktree'},
  {path:'/trees/main',label:'Project/main',branch:'main',kind:'worktree'},
  {path:'/trees/maintenance',label:'Project/maintenance',branch:'maintenance',kind:'worktree'}];
const usage={'/src/project':{count:5,lastUsed:1},'/trees/main':{count:3,lastUsed:2}};
const queries=['branch','worktree','branches','WORKTREES','main','MASTER',
  'worktree search','branch project','main project','master branch-tools',
  'main worktree','maintenance','/trees/main'];
process.stdout.write(JSON.stringify(Object.fromEntries(queries.map(query=>[query,
  window.LabSidebarScopes.ranked(rows,usage,query).map(row=>row.path)]))));
""")
    worktrees = ['/trees/main', '/trees/search', '/trees/maintenance']
    folders = ['/src/project', '/src/branch-tools', '/src']
    for keyword in ['branch','worktree','branches','WORKTREES']:
        assert result[keyword] == worktrees
    for keyword in ['main','MASTER']:
        assert result[keyword] == folders
    assert result['worktree search'] == ['/trees/search']
    assert result['branch project'] == worktrees
    assert result['main project'] == ['/src/project','/src']
    assert result['master branch-tools'] == ['/src/branch-tools']
    assert result['main worktree'] == []
    assert result['maintenance'] == ['/trees/maintenance']
    assert result['/trees/main'] == ['/trees/main','/trees/maintenance']


def test_double_click_opens_exact_scope_metadata_after_button_replacement():
    result = _run_node(helpers() + """
const selected=[],edited=[];
sidebarSelectScope=button=>selected.push(button.getAttribute('data-folder-path'));
window.LabScopeLinks={edit:(path,current,scope)=>edited.push({path,current,scope})};
_sidebarFileConfig.folderScopes=[{path:'/trees/topic',label:'project/topic',kind:'worktree'},
  {path:'/trees/other',label:'project/other',kind:'worktree'}];
_sidebarFileConfig.pinnedScopes=['/trees/topic','/trees/other'];
const button=path=>({getAttribute:name=>name==='data-base-root'?'/workspace':path});
sidebarActivateScope(button('/trees/topic'),{detail:1,timeStamp:100});
sidebarActivateScope(button('/trees/topic'),{detail:1,timeStamp:200});
sidebarActivateScope(button('/trees/other'),{detail:0,timeStamp:250});
sidebarActivateScope(button('/trees/other'),{detail:1,timeStamp:300});
sidebarActivateScope(button('/trees/topic'),{detail:1,timeStamp:350});
const current=edited[0].current();
_sidebarFileConfigScope='another-workspace';
const stale=edited[0].current();
sidebarEditScopeMetadata({getAttribute:()=>'/old-workspace'});
process.stdout.write(JSON.stringify({selected,edited:edited.map(({path,scope})=>({path,scope})),current,stale}));
""")
    assert result == {'selected':['/trees/topic','/trees/other','/trees/other','/trees/topic'],
                      'edited':[{'path':'/trees/topic','scope':{'label':'project/topic','kind':'worktree'}}],
                      'current':True,'stale':False}


def test_primary_folder_and_worktree_use_inline_controls_and_exact_branch_labels():
    result = _run_node(helpers() + _js_between('  function sidebarOpenRepositoryHistory(', '  function _sidebarGitHistoryButtonHtml(') + """
currentWorkspace.repos=[{path:'/workspace',name:'Checkpoint',branch:'master'}];
_sidebarFileConfig=_sidebarNormalizeFileConfig({folderScopes:[
 {path:'/src/Checkpoint',label:'Checkpoint',kind:'folder',branch:'master'},
 {path:'/trees/checkout',label:'Checkpoint/feature/login',kind:'worktree',branch:'feature/login',projectPath:'/src/Checkpoint'},
 {path:'/src/plain',label:'Plain folder',kind:'folder'}],
 selectedFolders:{'/workspace':'/src/Checkpoint'},pinnedScopes:['/trees/checkout']});
const rows=_sidebarVisibleScopes('/workspace').map(scope=>({label:_sidebarScopeDisplayLabel(scope),kind:scope.kind}));
const html=_sidebarFileScopeButtonsHtml('/workspace');
const history=[],button=(path,disabled=false)=>({disabled,hasAttribute:()=>true,getAttribute:name=>name==='data-base-root'?'/workspace':path});
function openRepositoryHistory(request){history.push(request)};
sidebarOpenRepositoryHistory(button('/src/Checkpoint'));
sidebarOpenRepositoryHistory(button('/trees/checkout',true));
_sidebarFileConfig.selectedFolders['/workspace']='/trees/checkout';
sidebarOpenRepositoryHistory(button('/src/Checkpoint'));
sidebarOpenRepositoryHistory(button('/trees/checkout'));
delete _sidebarFileConfig.selectedFolders['/workspace'];
const rootLabel=_sidebarScopeDisplayLabel(_sidebarVisibleScopes('/workspace')[0]);
currentWorkspace.repos[0].path='/workspace/nested';
const nestedRootLabel=_sidebarScopeDisplayLabel(_sidebarVisibleScopes('/workspace')[0]);
process.stdout.write(JSON.stringify({rows,rootLabel,nestedRootLabel,history,
 disabledHistory:Array.from(html.matchAll(/class="sidebar-repo-history"[^>]*disabled/g)).length,
 disabledTerminal:Array.from(html.matchAll(/class="sidebar-link-terminal"[^>]*disabled/g)).length,
 kindIcons:(html.match(/class="sidebar-scope-color"/g)||[]).length,
 plainLabel:_sidebarScopeDisplayLabel(_sidebarFolderScope('/src/plain')),
 noRepeatedBranch:!_sidebarWorktreePickerHtml('/workspace').includes('sidebar-worktree-current')}));
""")
    assert result == {'rows':[{'label':'Checkpoint/master','kind':'folder'},
                              {'label':'Checkpoint/feature/login','kind':'worktree'}],
                      'rootLabel':'Checkpoint/master','nestedRootLabel':'Root',
                      'history':[{'root':'/src/Checkpoint','label':'master'},
                                 {'root':'/trees/checkout','label':'feature/login'}],
                      'disabledHistory':1,'disabledTerminal':1,'kindIcons':2,
                      'plainLabel':'Plain folder','noRepeatedBranch':True}
