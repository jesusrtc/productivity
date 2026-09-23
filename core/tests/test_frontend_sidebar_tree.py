"""Tree construction preserves directory metadata, file identity and refreshes."""
from .test_frontend_terminal_ui import _js_between, _run_node


def test_tree_keeps_normalized_paths_metadata_and_original_file_objects():
    source = _js_between('  function buildSidebarTree(', '  function _sidebarEntryName(')
    result = _run_node(source + r'''
const files = [
  {path:'///docs//nested///first.md///', marker:1},
  {name:'root.md', marker:2},
  {path:'docs/nested/second.ipynb', pending:true, marker:3},
  {path:'///'}, {path:''}, null,
  {path:'docs/nested', type:'dir', is_symlink:true, symlink_target:'/target'},
  {path:'docs//nested/', type:'dir', label:'latest metadata'},
  {name:'empty', type:'dir'},
  {path:'docs/one.md', marker:4},
  {path:42, marker:5},
  {path:'docs/../literal.md', marker:6},
];
const before = JSON.stringify(files), tree = buildSidebarTree(files);
const node = tree.docs.nested;
console.log(JSON.stringify({
  tree,
  untouched:JSON.stringify(files) === before,
  identities:node.__files__[0] === files[0] && node.__files__[1] === files[2]
    && tree.__files__[0] === files[1] && tree.docs.__files__[0] === files[9],
}));
''')
    assert result == {
        'tree': {
            'docs': {
                'nested': {
                    '__entry__': {'path': 'docs/nested', 'name': 'nested', 'type': 'dir', 'label': 'latest metadata'},
                    '__files__': [
                        {'path': '///docs//nested///first.md///', 'marker': 1},
                        {'path': 'docs/nested/second.ipynb', 'pending': True, 'marker': 3},
                    ],
                },
                '__files__': [{'path': 'docs/one.md', 'marker': 4}],
                '..': {'__files__': [{'path': 'docs/../literal.md', 'marker': 6}]},
            },
            'empty': {'__entry__': {'name': 'empty', 'type': 'dir', 'path': 'empty'}},
            '__files__': [{'name': 'root.md', 'marker': 2}, {'path': 42, 'marker': 5}],
        },
        'untouched': True,
        'identities': True,
    }


def test_each_tree_build_uses_current_entries_without_retaining_old_folders():
    source = _js_between('  function buildSidebarTree(', '  function _sidebarEntryName(')
    result = _run_node(source + r'''
const old = buildSidebarTree([
  {path:'docs/old.md'}, {path:'removed/empty',type:'dir'},
  {path:'docs',type:'dir',is_symlink:true,symlink_target:'/before'},
]);
const fresh = buildSidebarTree([{path:'docs/new.md',mtime:42}]);
fresh.docs.__files__[0].mtime = 43;
console.log(JSON.stringify({old,fresh,empty:buildSidebarTree(null),distinct:old.docs !== fresh.docs}));
''')
    assert result['fresh'] == {'docs': {'__files__': [{'path': 'docs/new.md', 'mtime': 43}]}}
    assert result['old']['docs']['__files__'] == [{'path': 'docs/old.md'}]
    assert result['old']['docs']['__entry__']['symlink_target'] == '/before'
    assert 'removed' in result['old']
    assert result['empty'] == {}
    assert result['distinct'] is True
