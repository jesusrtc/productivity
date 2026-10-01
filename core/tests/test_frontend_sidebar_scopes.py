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
