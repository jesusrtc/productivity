"""Quick-file measurements check independent results and disposable ownership."""
from .test_frontend_logging import _run_node


def test_quick_file_expectations_keep_format_order_paths_and_input_data():
    result = _run_node("""
(async () => {
  const {expectedQuickFiles} = await import('./scripts/perf/quick_file_workload.mjs');
  const files = [
    {path:'docs/REPORT.md',mtime:10}, {path:'src/report.js',mtime:100},
    {path:'docs/report.ipynb',mtime:'20'}, {path:'docs/report',mtime:30},
    {path:'docs/.report',mtime:40}, {path:'docs/report.',mtime:50},
    {path:'docs/older-report.md'}, {path:'docs/report-dir',type:'dir'},
    {path:'docs/report-broken.md',broken:true}, {path:null}, null,
  ];
  const before=JSON.stringify(files), paths=rows=>rows.map(row=>row.path);
  process.stdout.write(JSON.stringify({
    preferred:paths(expectedQuickFiles(files,{trackMode:'extensions',extensions:['md','ipynb']},'REPORT')),
    scoped:paths(expectedQuickFiles(files,{trackMode:'extensions',extensions:['md','ipynb']},'DOCS report')),
    noExtension:paths(expectedQuickFiles(files,{trackMode:'extensions',extensions:['__none__']},'report')).slice(0,3),
    all:paths(expectedQuickFiles(files,{},'report')).slice(0,3),
    missing:expectedQuickFiles(files,{},'absent'),unchanged:before===JSON.stringify(files),
  }));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    assert result['preferred'] == ['docs/report.ipynb', 'docs/REPORT.md', 'docs/older-report.md',
                                   'src/report.js', 'docs/report.', 'docs/.report', 'docs/report']
    assert result['scoped'] == [path for path in result['preferred'] if path.startswith('docs/')]
    assert result['noExtension'] == ['docs/report.', 'docs/.report', 'docs/report']
    assert result['all'] == ['src/report.js', 'docs/report.', 'docs/.report']
    assert result['missing'] == [] and result['unchanged']


def test_quick_file_workload_rejects_nonfixture_scope_before_input():
    result = _run_node("""
(async () => {
  const {runQuickFileWorkload} = await import('./scripts/perf/quick_file_workload.mjs');
  const rejected=[];
  for(const workspaceRoot of ['/vault/workspaces','/tmp/user/vault/workspaces','/tmp/lab-navigation-test/workspaces']) {
    try {await runQuickFileWorkload(null,null,[],{workspaceRoot,samples:2,extraFiles:0});}
    catch(error){rejected.push(error.message);}
  }
  process.stdout.write(JSON.stringify(rejected));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    assert result == ['Quick-file actions require the disposable fixture'] * 3
