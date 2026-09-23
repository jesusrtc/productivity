"""Offscreen groups preserve file geometry and interactions in real Chrome."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('layout', ['folders', 'flat'])
def test_sidebar_offscreen_rendering_and_actions(tmp_path, layout):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    root = ROOT
    source=(root/'core/src/core/static/js/lab-app.js').read_text()
    def between(a,b):return source[source.index(a):source.index(b,source.index(a))]
    helpers=between('  function esc(s)', '  // ─── Explorer secondary-click menu')+between('  const TREE_EXPANDED_KEY', '  function applyIframeDarkMode')+between('  function _sidebarRecentTreeModel', '  function _sidebarConfigFolderCardHtml')
    helpers+=between('  function _sidebarHandleFileAction', '  async function openWorkspaceDoc(')
    helpers+=between('  const _GIT_ROW_CLASSES', '  function _sidebarPlaceGitBadge(')
    css=(root/'core/src/core/static/css/lab-shell.css').read_text()
    checks=r'''
    const assert=(v,m)=>{if(!v)throw Error(m)};
    const wait=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    (async()=>{try{
     const layout=FILE_LAYOUT;
     const files=Array.from({length:5000},(_,i)=>({path:`${layout==='folders'?'notes/batch-'+String(Math.floor(i/100)).padStart(3,'0'):'notes'}/file-${String(i).padStart(5,'0')}.${['md','py','json','sql'][i%4]}`,type:'file',mtime:1,is_symlink:i%17===0,symlink_target:'elsewhere'}));
     files[2444].path=files[2444].path.replace(/\.md$/, ` 'quoted' " & résumé.md`);
     const ref=document.getElementById('reference'), candidate=document.getElementById('sidebar');
     ref.innerHTML=_sidebarRecentSectionHtml(files,null,'/reference',{resolved:true});
     // Keep the original icon wrapper in the reference. Its pseudo-element
     // is disabled below so geometry compares old and new history buttons.
     ref.querySelectorAll('.sidebar-git-history').forEach(button=>button.innerHTML=_SIDEBAR_GITHUB_ICON);
     candidate.innerHTML=_sidebarRecentSectionHtml(files,null,'/candidate',{resolved:true});
     const first=candidate.querySelector('.sidebar-file');
     first.classList.add('active');
     const mutations=new MutationObserver(()=>{});
     mutations.observe(first,{attributes:true,attributeFilter:['class']});
     _gitSetRowClass(first,'');
     assert(mutations.takeRecords().length===0,'Unchanged clean state mutates class');
     for(const cls of _GIT_ROW_CLASSES){
      _gitSetRowClass(first,cls);mutations.takeRecords();
      assert(first.classList.contains(cls)&&first.classList.contains('active'),'Git state or selection lost');
      assert(_GIT_ROW_CLASSES.filter(c=>first.classList.contains(c)).length===1,'Old Git state retained');
      _gitSetRowClass(first,cls);
      assert(mutations.takeRecords().length===0,'Unchanged Git state mutates class');
     }
     _gitSetRowClass(first,'');mutations.disconnect();first.classList.remove('active');
     for(const zoom of [1,1.25])for(const width of [220,340]){
      document.body.style.zoom=zoom;
      for(const sidebar of [ref,candidate])sidebar.style.width=width+'px';
      await wait();
      assert(candidate.querySelectorAll('.sidebar-file').length===5000,'All file rows retained');
      assert(Math.abs(ref.scrollHeight-candidate.scrollHeight)<2,`Initial extent mismatch: ${ref.scrollHeight}/${candidate.scrollHeight} zoom=${zoom} width=${width}`);
      for(const index of [0,2444,4999,1200,0]){
       const a=ref.querySelectorAll('.sidebar-file')[index],b=candidate.querySelectorAll('.sidebar-file')[index];
       a.scrollIntoView({block:'center'});b.scrollIntoView({block:'center'});await wait();
       const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
       assert(Math.abs(ar.height-br.height)<.1,'Row height differs');
       const ah=a.querySelector('button').getBoundingClientRect(),bh=b.querySelector('button').getBoundingClientRect();
       assert(Math.abs(ah.width-bh.width)<.1&&Math.abs(ah.height-bh.height)<.1,'History button size differs');
       assert(Math.abs((ar.right-ah.right)-(br.right-bh.right))<.1&&Math.abs((ah.top-ar.top)-(bh.top-br.top))<.1,'History button position differs');
       assert(Math.abs(ref.scrollHeight-candidate.scrollHeight)<2,'Extent changed after scrolling');
       const hit=document.elementFromPoint(br.x+br.width/2,br.y+br.height/2);
       assert(hit&&b.contains(hit),'Wrong file at click coordinates '+index);
       hit.click();assert(calls.at(-1).kind==='file'&&calls.at(-1).path===files[index].path,'File action/root wrong');
       b.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));assert(calls.at(-1).kind==='modal','Double click missing');
       b.querySelector('button').click();assert(calls.at(-1).kind==='history','History action missing');
       const count=calls.length;
       b.querySelector('button').dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true}));
       assert(calls.length===count,'History double click opened a file modal');
       assert(b.draggable&&b.dataset.entryRoot==='/candidate','Drag/context metadata lost');
      }
     }
     document.body.style.zoom=1; await wait();
     for(const sidebar of [ref,candidate]){
      const folder=sidebar.querySelector(layout==='folders'?'[data-tree-path="notes/batch-024"]':'[data-tree-path="notes"]');
      folder.scrollIntoView({block:'center'});await wait();folder.click();await wait();
      assert(!document.getElementById(folder.dataset.treeTarget).classList.contains('open'),'Folder did not close');
      folder.click();await wait();assert(document.getElementById(folder.dataset.treeTarget).classList.contains('open'),'Folder did not reopen');
      folder.dispatchEvent(new MouseEvent('click',{bubbles:true,metaKey:true}));assert(calls.at(-1).kind==='folder','Cmd-click folder action missing');
     }
     candidate.scrollTop=0;ref.scrollTop=0;await wait();
     window.getSelection().removeAllRanges();
     assert(window.find('file-04999',false,false,true),'Find-in-page did not find reference');
     assert(window.find('file-04999',false,false,true),'Find-in-page did not find offscreen candidate');
     await wait();
     assert(window.getSelection().anchorNode.parentElement.closest('#sidebar'),'Find-in-page skipped contained files');
     window.getSelection().removeAllRanges();
     candidate.scrollTop=0;ref.scrollTop=0;await wait();
     document.getElementById('result').textContent=JSON.stringify({ok:true,extent:candidate.scrollHeight,rowHeight:candidate.querySelector('.sidebar-file').getBoundingClientRect().height,calls:calls.length});
    }catch(error){document.getElementById('result').textContent='FAIL: '+error.stack}})();
    '''.replace('FILE_LAYOUT', repr(layout))
    stubs=r'''
    let currentWorkspace={path:'/candidate'};
    const calls=[];
    const _sidebarCurrentSortMode=()=> 'name';
    const _sidebarSortSelectHtml=()=>'';
    const openWorkspaceDocFromFileClick=(path,options)=>calls.push({kind:'file',path,...options});
    const openWorkspaceDocModal=(path,options)=>calls.push({kind:'modal',path,...options});
    const openWorkspaceFolderModal=(path,options)=>calls.push({kind:'folder',path,...options});
    const openExplorerHistory=context=>calls.push({...context,kind:'history'});
    '''
    page=tmp_path/'sidebar.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+css+'''\n*{box-sizing:border-box}body{margin:0;background:#0d1117;--text-secondary:#aab;--text-primary:#eee;--border:#333;--accent:#68c;--tree-indent-guide:#334}aside.sidebar{position:fixed;top:50px;bottom:20px;height:auto!important;overflow:auto!important;width:340px;display:block}#reference{left:10px}#sidebar{left:500px}.reference .sidebar-recent-children{content-visibility:visible!important;contain-intrinsic-block-size:none!important}.reference .sidebar-git-history::before{content:none}</style><body><pre id="result">PENDING</pre><aside id="reference" class="sidebar reference"></aside><aside id="sidebar" class="sidebar"></aside><script>'''+stubs+helpers+checks+'</script>')
    with tempfile.TemporaryDirectory(prefix='lab-sidebar-qa-') as directory:
     profile=Path(directory)/'chrome'
     chrome=subprocess.Popen([chrome,'--headless=new','--no-first-run','--disable-background-networking','--window-size=1400,1000','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
     try:
      deadline=time.monotonic()+10
      while not (profile/'DevToolsActivePort').exists():
       if chrome.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Chrome did not start')
       time.sleep(.05)
      r=subprocess.run(['node',str(root/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'rendered.html'),str(tmp_path/'sidebar.png')],env={**os.environ,'LAB_UI_AUTH_COOKIE':''},capture_output=True,text=True,timeout=45)
      assert r.returncode == 0, r.stderr
      rendered=(tmp_path/'rendered.html').read_text()
      match=re.search(r'<pre id="result">(.*?)</pre>',rendered,re.S)
      assert match and '&quot;ok&quot;:true' in match.group(1).replace(chr(34), '&quot;'), match.group(1) if match else 'No result'
     finally:
      if chrome.poll() is None:os.killpg(chrome.pid,signal.SIGTERM)
      chrome.wait(timeout=5)
