from .test_frontend_terminal_ui import _js_between, _run_node


def test_link_transfer_updates_both_tabs_and_ignores_a_late_navigation():
    helpers = _js_between("  function _termLinkContext()", "  function _termSessionsLinkedToContext(")
    result = _run_node(helpers + """
let workspace = 'home', vault = null, renders = 0;
const _termActiveWorkspaceId = () => workspace, _termVaultId = () => vault;
const _termSessionsCache = new Map(), _termSessionsKey = (w,v) => w + v;
const termRenderSessionList = () => renders++, _termRenderActiveSessionHeader = () => {};
let termSessions = [{name:'a',logical_name:'first',linked_file:{path:'a.md'}, linked_scope:{root:'/repo'}},
  {name:'b',logical_name:'second'}];
let navigate = false;
const fetch = async () => {
  if (navigate) { workspace = 'elsewhere'; termSessions = [{name:'other'}]; }
  return {ok:true, json:async () => ({session:{name:'second',linked_file:{path:'a.md'}},
    displaced:[{current_workspace:true,workspace_id:'home',vault:'actual-vault',
      session:{name:'first',linked_scope:{root:'/repo'}}}]})};
};
(async () => {
  await _termPatchLinks(termSessions[1], {});
  const after = JSON.parse(JSON.stringify(termSessions));
  navigate = true;
  await _termPatchLinks(termSessions[1], {});
  process.stdout.write(JSON.stringify({after, current:termSessions, renders}));
})();
""")
    assert result["after"][0]["linked_file"] is None
    assert result["after"][0]["linked_scope"] == {"root": "/repo"}
    assert result["after"][1]["linked_file"] == {"path": "a.md"}
    assert result["current"] == [{"name": "other"}]
    assert result["renders"] == 1


def test_direct_unlink_removes_only_the_selected_association():
    helper = _js_between("  async function termUnlinkTarget(", "  function _termLinkDropContext(")
    result = _run_node(helper + """
const termSessions = [{name:'one',label:'a.md',linked_file:{path:'docs/a.md'}}];
const _termLinkedFileName = path => path.split('/').pop();
const patches = [], _termPatchLinks = async (s,patch) => patches.push(patch);
const explorerToast = () => {};
(async () => {
  await termUnlinkTarget('one','file');
  termSessions[0].label = 'Custom name';
  await termUnlinkTarget('one','file');
  await termUnlinkTarget('one','scope');
  process.stdout.write(JSON.stringify(patches));
})();
""")
    assert result == [{"linked_file": None, "label": None},
                      {"linked_file": None}, {"linked_scope": None}]


def test_code_scope_link_uses_shared_terminal_owner_and_file_link_cascades():
    helpers = _js_between("  function _termLinkContext()", "  function _termSessionsLinkedToContext(")
    helpers += _js_between("  async function termLinkTarget(", "  async function termUnlinkTarget(")
    result = _run_node(helpers + """
const _termActiveWorkspaceId = () => 'demo', _termVaultId = () => 'client';
const _termSessionsCache = new Map();
const source = {workspace_id:'__assistant__',vault:'__assistant__',logical_name:'codex'};
const doc = {assistant_root:'/assistant',document_id:'document',title:'Document title'};
let termSessions = [{name:'running-process',logical_name:'@document:running-process',
  label:'My Assistant name',document_source:source,linked_task:doc}];
const scope = {base_root:'/workspace',project_root:'/repo',root:'/trees/feature',worktree:'/trees/feature',label:'Code · feature'};
const _termScopeForFile = async () => scope;
const _termLinkedAbsolutePath = (root,path) => root + '/' + path;
const _termLinkedFileName = path => path.split('/').pop();
const _copyToClipboard = async () => true, explorerToast = () => {};
let refreshes = 0;
const _termRefreshSessionsForWorkspaceId = async () => {refreshes++;};
const requests = [];
const fetch = async (url, options) => {
  requests.push(JSON.parse(options.body));
  return {ok:true,json:async () => ({session:{name:'codex'}})};
};
(async () => {
  await termLinkTarget({kind:'folder',root:scope.root,path:'',scope}, 'running-process');
  await termLinkTarget({kind:'file',root:scope.root,path:'src/example.py'}, 'running-process');
  process.stdout.write(JSON.stringify({requests, refreshes, session:termSessions[0]}));
})();
""")
    folder, file = result['requests']
    assert folder == {'workspace_id':'__assistant__', 'vault':'__assistant__', 'name':'codex',
                      'linked_scope':file['linked_scope']}
    assert file['linked_file'] == {'root':'/trees/feature', 'path':'src/example.py'}
    assert file['linked_scope']['root'] == '/trees/feature'
    assert 'linked_task' not in file
    assert result['session']['label'] == 'My Assistant name'
    assert result['session']['linked_task']['document_id'] == 'document'
    assert result['refreshes'] == 2
