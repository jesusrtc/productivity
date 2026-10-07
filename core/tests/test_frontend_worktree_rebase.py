"""Native browser checks for the exact-worktree pull/rebase action and results."""
import pytest

from .test_frontend_project_cache import _check_project_html
from .test_frontend_terminal_ui import _js_between, LAB_SHELL_CSS


@pytest.mark.parametrize('width', [280, 480])
def test_native_pull_arrow_pending_navigation_and_conflict_output(tmp_path, width):
    source = _js_between('  function _sidebarScopeDisplayLabel(', '  function _sidebarVisibleScopes(')
    setup = r'''
const _SIDEBAR_GITHUB_ICON='<span class="sidebar-github-icon"></span>';
let selected='/trees/feature',_sidebarFileConfigScope='workspace',_sidebarScopeTransition=null;
const _sidebarFileConfig={pinnedScopes:['/trees/other']},_sidebarWorktreeBaseRoot=()=>'/workspace',_sidebarScopedRoot=()=>selected;
const rows=[{path:'/workspace',label:'Project/master',kind:'folder'},
 {path:'/trees/feature',label:'Project/feature/long-name',kind:'worktree',color:'#58a6ff'},
 {path:'/trees/other',label:'Project/other',kind:'worktree',color:'#ff7b72'}];
const _sidebarVisibleScopes=()=>rows,_sidebarValidColor=c=>c||'#8b949e';
const esc=String,escAttr=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const requests=[],refreshes=[],toasts=[];let release;
window.fetch=(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return new Promise(r=>release=data=>r({ok:data.status==='ok',json:async()=>data}));};
const explorerToast=(...args)=>toasts.push(args),_refreshSidebarAfterFileConfig=async()=>refreshes.push(selected);
function _sidebarRenderScopeButtons(){document.getElementById('sidebar').innerHTML=_sidebarFileScopeButtonsHtml('/workspace');}
const assert=(value,label)=>{if(!value)throw Error(label)},q=s=>document.querySelector(s),tick=()=>new Promise(r=>setTimeout(r,0));
const arrow=path=>q('.sidebar-worktree-pull[data-worktree-rebase-path="'+path+'"]');
'''
    checks = r'''
(async()=>{
 _sidebarRenderScopeButtons();
 assert(document.querySelectorAll('.sidebar-worktree-pull').length===2,'only worktrees get an arrow');
 assert(document.querySelectorAll('.sidebar-link-terminal').length===3,'terminal action remains beside arrow');
 assert(!arrow('/trees/feature').disabled&&arrow('/trees/other').disabled,'only selected checkout is enabled');
 assert(arrow('/trees/feature').querySelector('svg')&&arrow('/trees/feature').getAttribute('aria-label').includes('origin/master'),'down arrow has accessible target');
 const bounds=arrow('/trees/feature').getBoundingClientRect(),rail=q('#sidebar').getBoundingClientRect();
 assert(bounds.width===23&&bounds.right<=rail.right,'arrow fits the narrow scope row');
 const old=arrow('/trees/feature');old.click();old.click();
 assert(requests.length===1&&requests[0].url==='/api/git/worktree-pull-rebase'&&requests[0].body.path==='/trees/feature','duplicate clicks send only the captured checkout');
 assert(arrow('/trees/feature').disabled&&arrow('/trees/feature').getAttribute('aria-busy')==='true','repaint retains busy action');
 assert(q('.sidebar-worktree-rebase-result').open&&q('[data-worktree]').textContent==='/trees/feature','progress result is visible for captured checkout');
 selected='/trees/other';_sidebarRenderScopeButtons();sidebarPullRebaseWorktree(old);
 release({status:'ok',message:'Feature rebased.',output:'<img src=x onerror="window.bad=true">\nGit output'});await tick();await tick();
 assert(refreshes.length===0&&selected==='/trees/other','late result cannot refresh a different checkout');
 assert(q('[data-output]').textContent.includes('<img')&&!q('[data-output] img')&&!window.bad,'Git output stays plain text');
 assert(!arrow('/trees/other').disabled&&arrow('/trees/feature').disabled,'busy state clears in the current sidebar');
 q('[data-close]').click();
 arrow('/trees/other').click();
 release({status:'conflict',message:'Rebase paused on conflicts.',output:'CONFLICT in shared.txt',rebase_paused:true});await tick();await tick();
 assert(q('.sidebar-worktree-rebase-result').classList.contains('error')&&!q('[data-guidance]').hidden&&q('[data-guidance]').textContent.includes('git rebase --abort'),'paused rebase offers continue and abort guidance');
 assert(refreshes.join(',')==='/trees/other'&&q('#draft').value==='Keep this draft','same-checkout refresh preserves unrelated draft');
 q('[data-close]').click();arrow('/trees/other').click();q('[data-close]').click();
 release({status:'error',detail:'Remote master not found'});await tick();await tick();
 assert(toasts.at(-1)[0].includes('Project/other: Remote master not found')&&!_sidebarWorktreeRebases.size,'closing progress keeps final error feedback and clears pending work');
 window.LAB_IS_ADMIN=false;_sidebarRenderScopeButtons();assert(!q('.sidebar-worktree-pull'),'non-admin has no mutating action');
 document.body.dataset.result='pass';
})().catch(error=>{document.body.dataset.result='fail';document.body.append(error.stack||String(error));});
'''
    css = LAB_SHELL_CSS.read_text()
    html = f'<!doctype html><meta charset="utf-8"><style>{css} #sidebar{{width:{width}px;box-sizing:border-box;position:static;overflow:auto}}</style><body><aside id="sidebar"></aside><textarea id="draft">Keep this draft</textarea><script>'+setup+source+checks+'</script>'
    _check_project_html(tmp_path, html)
