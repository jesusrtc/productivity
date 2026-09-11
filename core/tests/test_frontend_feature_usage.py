from .test_frontend_terminal_ui import _js_between, _run_node


def test_link_counters_distinguish_gestures_and_ignore_failures():
    result = _run_node('''
const events = [], window = {labFeatureUsage: name => events.push(name)};
const termSessions = [{name:'one',logical_name:'one'}];
const _termLinkContext = () => ({workspaceId:'home',vaultId:'v'});
const _termActiveWorkspaceId = () => 'home', _termVaultId = () => 'v';
const _termLinkedAbsolutePath = () => '/repo/doc.md';
const _termLinkedFileName = () => 'doc.md';
const _copyToClipboard = async () => true;
const _termScopeForFile = async () => ({root:'/repo'});
const explorerToast = () => {};
let fail = false;
const _termPatchLinks = async () => {if(fail) throw Error('not saved');};
''' + _js_between('  async function termLinkTarget(', '  async function termUnlinkTarget(') + '''
(async () => {
  const ctx = {kind:'file',root:'/repo',path:'doc.md'};
  await termLinkTarget(ctx, 'one');
  await termLinkTarget(ctx, 'one', 'drag and drop');
  fail = true;
  await termLinkTarget(ctx, 'one', 'drag and drop');
  await termLinkTarget(ctx, 'missing');
  console.log(JSON.stringify(events));
})();
''')
    assert result == ['Link terminal to document (secondary click)',
                      'Link terminal to document (drag and drop)']


def test_collector_uses_local_day_and_never_blocks_action():
    result = _run_node('''
const calls = [], window = {}, UI_CHECK = false;
class Date {getFullYear(){return 2026;} getMonth(){return 8;} getDate(){return 10;}}
const fetch = (url, opts) => {calls.push({url,...opts}); return Promise.reject(Error('offline'));};
''' + _js_between('  window.labFeatureUsage = function', '  let currentRepo = null;') + '''
window.labFeatureUsage('Create file');
setTimeout(() => console.log(JSON.stringify(calls)),0);
''')
    assert len(result) == 1
    import json
    assert json.loads(result[0]['body']) == {'day': '2026-09-10', 'feature': 'Create file'}
    assert result[0]['keepalive'] is True


def test_usage_view_date_filter_copy_and_clear():
    result = _run_node('''
const UI_CHECK = true, window = {}, elements = {}, calls = [], copied = [];
for (const id of ['adminLogOutput','adminLogTitle','adminLogCount','adminLogStatus','adminLogCopyButton',
  'adminLogFlushButton','adminLogLimitLabel','adminUsageDateLabel','adminUsageAllLabel','adminUsageDate','adminUsageAll']) {
  elements[id] = {attrs:{},textContent:'',innerHTML:'',setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];}};
}
elements.adminUsageDate.value = '2026-09-11';
const document = {getElementById:id=>elements[id],querySelectorAll:()=>[]};
const esc = text => String(text).replaceAll('<','&lt;');
const _copyToClipboard = async text => {copied.push(text); return true;};
const confirm = () => true;
let cleared = false;
const fetch = async (url, opts={}) => {
  calls.push([url,opts.method||'GET']);
  if(opts.method==='DELETE') {cleared=true; return {ok:true,json:async()=>({cleared:['main']})};}
  return {ok:true,json:async()=>({total_usage:cleared?0:3,entries:cleared?[]:[
    {date:'2026-09-11',feature:'Create file',usage_count:2},
    {date:'2026-09-11',feature:'Create workspace (+ button)',usage_count:1}]})};
};
''' + _js_between('  function _adminLogLabel(file)', '  // Toggle hidden-files visibility for the productivity sidebar.') + '''
(async()=>{
  await adminRefreshLogs('usage');
  await adminCopyLogs(elements.adminLogCopyButton);
  const title=elements.adminLogTitle.textContent, count=elements.adminLogCount.textContent;
  const filterVisible=!elements.adminUsageDateLabel.hidden && elements.adminLogLimitLabel.hidden;
  elements.adminUsageAll.checked=true;
  await adminRefreshLogs('usage');
  await adminFlushLogs(elements.adminLogFlushButton);
  console.log(JSON.stringify({title,count,filterVisible,copied,calls,empty:elements.adminLogOutput.innerHTML}));
})();
''')
    assert result['title'] == 'Feature usage'
    assert result['filterVisible'] is True
    assert 'most used first' in result['count']
    assert result['copied'] == ['2026-09-11  Create file - 2\n2026-09-11  Create workspace (+ button) - 1']
    assert result['calls'][0] == ['/api/log/usage?day=2026-09-11', 'GET']
    assert result['calls'][1] == ['/api/log/usage', 'GET']
    assert result['calls'][2] == ['/api/log/usage', 'DELETE']
    assert 'No feature usage' in result['empty']
