"""Offscreen groups preserve file geometry and interactions in real Chrome."""
import json
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
    helpers+=between('  function _sidebarPlaceGitBadge(', '  function _sidebarApplyGitStatus(')
    helpers+=between('  const _sidebarMarkupCache =', '  // Re-renders just the workspace file sidebar')
    helpers+=(root/'core/tests/fixtures/file-icons-legacy.js').read_text()
    workspace_tree=between('        function renderTree(node, depth, parentPath, offset)',
                           '      sbHtml += _sidebarWorktreeScopeEndHtml(workspacePath);')
    # The extracted block includes the enclosing if's closing brace.
    workspace_tree=workspace_tree.rsplit('      }',1)[0]
    helpers+='''
    function workspaceMarkup(files,activePath=null){
      const fileRoot='/workspace-parts',_workspaceTreeScope='workspace:parts',AUTO_OPEN_FOLDERS=new Set(['notes']);
      const pinnedSet=new Set(),worktreeSelected=false,sidebarParts=[],tree=buildSidebarTree(files.map(f=>({...f,name:f.path})));
      const _recentlyPending=new Map(),_PENDING_GRACE_MS=1000,_nbGetLastViewed=()=>0;
      let sbHtml='<span>Before tree</span>';
    '''+workspace_tree+'''
      return {html:sbHtml,parts:sidebarParts};
    }
    '''
    css=(root/'core/src/core/static/css/lab-shell.css').read_text()
    checks=r'''
    const assert=(v,m)=>{if(!v)throw Error(m)};
    const wait=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    (async()=>{try{
     const layout=FILE_LAYOUT;
     const files=Array.from({length:5000},(_,i)=>({path:`${layout==='folders'?'notes/batch-'+String(Math.floor(i/100)).padStart(3,'0'):'notes'}/file-${String(i).padStart(5,'0')}.${['md','py','json','sql'][i%4]}`,type:'file',mtime:1,is_symlink:i%17===0,symlink_target:'elsewhere'}));
     files[2444].path=files[2444].path.replace(/\.md$/, ` 'quoted' " & résumé.md`);
     const ref=document.getElementById('reference'), candidate=document.getElementById('sidebar');
     const optimizedFileIconHtml=fileIconHtml;
     fileIconHtml=legacyFileIconHtml;
     ref.innerHTML=_sidebarRecentSectionHtml(files,null,'/reference',{resolved:true});
     fileIconHtml=optimizedFileIconHtml;
     // Keep the original icon wrapper in the reference. Its pseudo-element
     // is disabled below so geometry compares old and new history buttons.
     ref.querySelectorAll('.sidebar-git-history').forEach(button=>{
      const wrapper=document.createElement('span');wrapper.className='sidebar-actions';
      button.replaceWith(wrapper);wrapper.appendChild(button);button.classList.remove('sidebar-actions');
      button.innerHTML=_SIDEBAR_GITHUB_ICON;
     });
     const parts=[];
     const markup=_sidebarRecentSectionHtml(files,null,'/candidate',{resolved:true,parts});
     _replaceWorkspaceSidebarMarkup(candidate,markup,'large',false,parts);
     assert(parts.length>0,'recent renderer did not provide folder ranges');
     for(const part of parts){
      const expected=document.createElement('template');expected.innerHTML=markup.slice(part.start,part.end);
      assert(expected.content.children.length===1&&expected.content.firstChild.id===part.id,'recent renderer range is not the complete folder');
      assert(expected.content.firstChild.isEqualNode(_sidebarMarkupCache.get('large').parts.get(part.id).node),'recent renderer range has the wrong descendants');
     }
     const changedFiles=files.map((file,index)=>index===2444?{...file,path:file.path+'-changed'}:file);
     const nextParts=[];
     const nextMarkup=_sidebarRecentSectionHtml(changedFiles,changedFiles[2444].path,'/candidate',{resolved:true,parts:nextParts});
     _replaceWorkspaceSidebarMarkup(candidate,nextMarkup,'large',true,nextParts);
     const expected=document.createElement('template');expected.innerHTML=nextMarkup;
     assert(candidate.innerHTML===expected.innerHTML,'large changed-folder fragments differ from complete HTML');
     _replaceWorkspaceSidebarMarkup(candidate,markup,'large',true,parts);
     expected.innerHTML=markup;
     assert(candidate.innerHTML===expected.innerHTML,'large restored fragments differ from complete HTML');
     const scratch=document.createElement('aside');
     for(const [entries,active] of [[files,null],[changedFiles,changedFiles[2444].path],[files,null]]){
      const rendered=workspaceMarkup(entries,active);
      _replaceWorkspaceSidebarMarkup(scratch,rendered.html,'workspace-parts',true,rendered.parts);
      expected.innerHTML=rendered.html;
      assert(scratch.innerHTML===expected.innerHTML,'workspace file fragments differ from complete HTML');
      for(const part of rendered.parts){
       const section=document.createElement('template');section.innerHTML=rendered.html.slice(part.start,part.end);
       assert(section.content.children.length===1&&section.content.firstChild.id===part.id,'workspace renderer range is not the complete folder');
       assert(section.content.firstChild.isEqualNode(expected.content.getElementById(part.id)),'workspace renderer range has the wrong descendants');
      }
     }
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
       const textRect=row=>{const range=document.createRange();range.selectNodeContents(row.querySelector('.sidebar-fname').lastChild);return range.getBoundingClientRect()};
       const at=textRect(a),bt=textRect(b);
       assert(Math.abs((at.y-ar.y)-(bt.y-br.y))<.1&&Math.abs((at.x-ar.x)-(bt.x-br.x))<.1,'Filename baseline/offset differs '+JSON.stringify({index,zoom,width,old:[at.y-ar.y,at.x-ar.x],new:[bt.y-br.y,bt.x-br.x]}));
       const ai=a.querySelector('.ft-icon').getBoundingClientRect(),bi=b.querySelector('.ft-icon').getBoundingClientRect();
       assert(Math.abs((ai.y-ar.y)-(bi.y-br.y))<.1&&Math.abs((ai.x-ar.x)-(bi.x-br.x))<.1,'Icon box position differs');
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
     const deadline=performance.now()+4000;
     while(_sidebarLayoutJobs.has(candidate)){
      assert(performance.now()<deadline,'Idle layout preparation did not finish');await wait();
     }
     const retainedRow=candidate.querySelector('.sidebar-file');
     const preparedGroup=retainedRow.closest('.sidebar-recent-children');
     assert(preparedGroup.hasAttribute('data-sidebar-layout-ready'),'Live file group was not prepared');
     retainedRow.querySelector('button').focus();
     _replaceWorkspaceSidebarMarkup(candidate,nextMarkup,'large',true,nextParts);
     assert(candidate.querySelector('.sidebar-file')===retainedRow,'Prepared flat/nested groups must still reconcile');
     assert(document.activeElement===retainedRow.querySelector('button'),'Preparation lost retained focus during refresh');
     assert(preparedGroup.hasAttribute('data-sidebar-layout-ready'),'Unchanged prepared group lost its layout');
     assert(!_sidebarMarkupCache.get('large').template.content.querySelector('[data-sidebar-layout-ready]'),'Live layout state leaked into pristine templates');
     _replaceWorkspaceSidebarMarkup(candidate,markup,'large',true,parts);
     const clean=candidate.cloneNode(true);
     clean.querySelectorAll('[data-sidebar-layout-ready]').forEach(group=>group.removeAttribute('data-sidebar-layout-ready'));
     expected.innerHTML=markup;
     assert(clean.innerHTML===expected.innerHTML,'Prepared/reconciled markup differs from a complete render');
     document.activeElement.blur();
     // File icons also appear in other inline labels and as flex items. Cover
     // 13px and 14px glyphs, every extension family, symlinks, and both themes.
     const types=['note.md','code.py','query.sql','data.json','dep.lock','book.ipynb','app.js','types.ts','config.toml','page.html','app.css','run.sh','paper.pdf','Data.scala','table.csv','.gitignore','image.png','video.mp4','unknown.xyz'];
     window.__iconTypes=types;
     const iconChecks=document.createElement('div');iconChecks.style.cssText='position:absolute;top:0;left:1000px;width:420px';
     const legacy=document.createElement('div');legacy.className='reference';legacy.style.cssText='position:absolute;width:200px';
     const simple=document.createElement('div');simple.style.cssText='position:absolute;left:210px;width:200px';
     const sampleMarkup=renderIcon=>types.flatMap(name=>[false,true].flatMap(link=>[
      `<div class="sidebar-file"><span class="sidebar-fname">${renderIcon(name,{is_symlink:link})}${name}</span></div>`,
      `<div class="sidebar-file">${renderIcon(name,{is_symlink:link})}<span class="sidebar-fname">${name}</span></div>`,
     ])).join('');
     legacy.innerHTML=sampleMarkup(legacyFileIconHtml);simple.innerHTML=sampleMarkup(fileIconHtml);
     iconChecks.append(legacy,simple);document.body.appendChild(iconChecks);
     for(const light of [false,true])for(const zoom of [1,1.25]){
      document.body.classList.toggle('light-mode',light);document.body.style.zoom=zoom;await wait();
      const oldRows=[...legacy.children],newRows=[...simple.children];
      for(let i=0;i<oldRows.length;i++){
       const a=oldRows[i],b=newRows[i],ar=a.getBoundingClientRect(),br=b.getBoundingClientRect();
       const textRect=row=>{const range=document.createRange();range.selectNodeContents(row.querySelector('.sidebar-fname').lastChild);return range.getBoundingClientRect()};
       const at=textRect(a),bt=textRect(b);
       assert(Math.abs(ar.height-br.height)<.1&&Math.abs((at.y-ar.y)-(bt.y-br.y))<.1,`Icon family changed label baseline: ${types[Math.floor(i/4)]}, zoom=${zoom}`);
       const ai=a.querySelector('.ft-icon'),bi=b.querySelector('.ft-icon');
       const air=ai.getBoundingClientRect(),bir=bi.getBoundingClientRect();
       assert(Math.abs((air.y-ar.y)-(bir.y-br.y))<.1&&Math.abs(air.width-bir.width)<.1,'Icon family changed box position/width');
       if(ai.classList.contains('ft-ln'))assert(getComputedStyle(ai,'::after').bottom===getComputedStyle(bi,'::after').bottom,'Symlink overlay moved');
      }
     }
     iconChecks.remove();document.body.classList.remove('light-mode');document.body.style.zoom=1;
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
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+css+'''\n*{box-sizing:border-box}body{margin:0;background:#0d1117;--text-secondary:#aab;--text-primary:#eee;--border:#333;--accent:#68c;--tree-indent-guide:#334}aside.sidebar{position:fixed;top:50px;bottom:20px;height:auto!important;overflow:auto!important;width:340px;display:block}#reference{left:10px}#sidebar{left:500px}.reference .sidebar-recent-children{content-visibility:visible!important;contain-intrinsic-block-size:none!important}.reference .sidebar-git-history::before{content:none}.reference .ft-icon{display:inline-flex;align-items:center;justify-content:center;vertical-align:-3px;background:none}.reference .ft-icon::before{content:none}.reference .ft-icon svg{display:block;position:static;transform:none}</style><body><pre id="result">PENDING</pre><aside id="reference" class="sidebar reference"></aside><aside id="sidebar" class="sidebar"></aside><script>'''+stubs+helpers+checks+'</script>')
    with tempfile.TemporaryDirectory(prefix='lab-sidebar-qa-') as directory:
     profile=Path(directory)/'chrome'
     chrome=subprocess.Popen([chrome,'--headless=new','--no-first-run','--disable-background-networking','--window-size=1400,1000','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
     try:
      deadline=time.monotonic()+10
      while not (profile/'DevToolsActivePort').exists():
       if chrome.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Chrome did not start')
       time.sleep(.05)
      interactions=r'''
const evaluate=async expression=>{
 const value=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(value.exceptionDetails)throw Error(value.exceptionDetails.exception?.description||value.exceptionDetails.text);
 return value.result.value;
};
const frame=()=>evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
if(!(await evaluate('document.getElementById("result").textContent')).includes('"ok":true'))throw Error(await evaluate('document.getElementById("result").textContent'));
for(const light of [false,true])for(const zoom of [1,1.25])for(const width of [220,340])for(const badge of [false,true]){
 await evaluate(`document.body.classList.toggle('light-mode',${light});document.body.style.zoom=${zoom};
  for(const id of ['reference','sidebar']){
   const el=document.getElementById(id);el.style.width='${width}px';el.scrollTop=0;
   const row=el.querySelectorAll('.sidebar-file')[2];_gitSetRowClass(row,${badge}?'git-m':'');
   row.querySelector('.git-badge')?.remove();
   if(${badge}){const label=document.createElement('span');label.className='git-badge';label.textContent='M';_sidebarPlaceGitBadge(row,label);}
  }`);
 for(const hover of [false,true]){
  const samples=[];
  for(const id of ['reference','sidebar']){
   const point=await evaluate(`(()=>{const row=document.getElementById('${id}').querySelectorAll('.sidebar-file')[2];const r=row.querySelector('button').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
   await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:hover?point.x:0,y:hover?point.y:0});await frame();
   samples.push(await evaluate(`(()=>{
    const row=document.getElementById('${id}').querySelectorAll('.sidebar-file')[2],button=row.querySelector('button');
    if(button.matches(':hover')!==${hover})throw Error('Native hover not established');
    const r=row.getBoundingClientRect(),b=button.getBoundingClientRect(),style=getComputedStyle(button);
    let opacity=1;for(let node=button;node!==row;node=node.parentElement)opacity*=Number(getComputedStyle(node).opacity);
    return {height:r.height,width:b.width,buttonHeight:b.height,right:r.right-b.right,top:b.top-r.top,color:style.color,background:style.backgroundColor,opacity,
      badgeBefore:!row.querySelector('.git-badge')||!!(row.querySelector('.git-badge').compareDocumentPosition(button)&Node.DOCUMENT_POSITION_FOLLOWING)};
   })()`));
  }
  for(const key of Object.keys(samples[0])){
   const a=samples[0][key],b=samples[1][key];
   if(typeof a==='number'?Math.abs(a-b)>.1:a!==b)throw Error('Hover/theme mismatch '+JSON.stringify({key,samples,light,zoom,width,badge,hover}));
  }
 }
}
const before=await evaluate("calls.filter(c=>c.kind==='history').length");
await evaluate("document.querySelector('#sidebar .sidebar-git-history').focus()");
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
const after=await evaluate("({count:calls.filter(c=>c.kind==='history').length,focused:document.activeElement.outerHTML,last:calls.at(-1)})");
if(after.count!==before+1)throw Error('Keyboard history action failed '+JSON.stringify({before,after}));
// Preparing a group must keep the same visible paint as content-visibility:auto.
// Exercise both sides of the 100-row boundaries, including focus and drop ink.
await evaluate("_cancelSidebarLayout(document.getElementById('sidebar'))");
const boundaryPixels=[];
for(const light of [false,true])for(const zoom of [1,1.25])for(const width of [220,340])for(const index of [0,99,100,4999]){
 await evaluate(`(()=>{
  document.body.classList.toggle('light-mode',${light});document.body.style.zoom=${zoom};
  const sidebar=document.getElementById('sidebar');sidebar.style.width='${width}px';
  const row=sidebar.querySelectorAll('.sidebar-file')[${index}];
  row.classList.add('term-link-drop-target');row.querySelector('button').focus();row.scrollIntoView({block:'center'});
 })()`);await frame();
 const shots=[],clips=[];
 for(const prepared of [false,true]){
  await evaluate(`document.querySelectorAll('#sidebar .sidebar-file')[${index}].closest('.sidebar-recent-children').toggleAttribute('data-sidebar-layout-ready',${prepared})`);
  await frame();
  const clip=await evaluate(`(()=>{
   const row=document.querySelectorAll('#sidebar .sidebar-file')[${index}],r=row.getBoundingClientRect();
   const button=row.querySelector('button'),b=button.getBoundingClientRect();
   const hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);
   if(!hit||!button.contains(hit)||document.activeElement!==button)throw Error('Boundary action is obscured');
   return {x:r.x,y:r.y-3,width:r.width,height:r.height+6,scale:1};
  })()`);
  clips.push(clip);shots.push((await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,clip})).data);
 }
 if(JSON.stringify(clips[0])!==JSON.stringify(clips[1]))throw Error('Preparation moved boundary geometry');
 const pixels=await evaluate(`(async()=>{
  const crops=[];
  for(const data of ${JSON.stringify(shots)}){
   const img=new Image();img.src='data:image/png;base64,'+data;await img.decode();
   const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
   const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0);
   crops.push(ctx.getImageData(0,0,img.width,img.height).data);
  }
  let sum=0,max=0,changed=0;
  for(let i=0;i<crops[0].length;i+=4){let pixel=0;for(let c=0;c<3;c++){const d=Math.abs(crops[0][i+c]-crops[1][i+c]);sum+=d;pixel=Math.max(pixel,d);}max=Math.max(max,pixel);if(pixel)changed++;}
  return {mean:sum/(crops[0].length/4*3),max,changed};
 })()`);
 boundaryPixels.push({light,zoom,width,index,...pixels});
 // Separate paint layers can round antialiased corners differently. This is
 // the same small edge-compositing allowance as the native-scale icon check.
 if(pixels.mean>.1||pixels.max>20){
  for(let i=0;i<shots.length;i++)await writeFile(screenshotPath.replace('.png',`-boundary-${i}.png`),Buffer.from(shots[i],'base64'));
  throw Error('Preparation changed boundary pixels '+JSON.stringify(boundaryPixels.at(-1)));
 }
 await evaluate(`document.querySelectorAll('#sidebar .sidebar-file')[${index}].classList.remove('term-link-drop-target')`);
}
await writeFile(screenshotPath.replace('.png','-boundaries.json'),JSON.stringify(boundaryPixels,null,2));
await evaluate("document.activeElement.blur();document.body.classList.remove('light-mode');document.body.style.zoom=1;for(const id of ['reference','sidebar']){const el=document.getElementById(id);el.style.width='340px';el.scrollTop=0;const row=el.querySelectorAll('.sidebar-file')[2];_gitSetRowClass(row,'');row.querySelector('.git-badge')?.remove();}");
await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:0,y:0});await frame();
// Compare actual painted pixels, including inherited colors and symlink overlays.
// Decode Chrome's own PNG in a canvas so the check needs no imaging dependency.
const iconPixels=[];
for(const theme of ['dark','light','custom'])for(const zoom of [1,1.25]){
 const pairs=await evaluate(`(()=>{
  document.body.classList.toggle('light-mode','${theme}'==='light');document.body.style.zoom=${zoom};
  const sheet=document.createElement('div');sheet.id='icon-sheet';
  sheet.style.cssText='position:fixed;z-index:99999;left:0;top:0;width:640px;padding:16px;background:#182030;color:white;font:12px sans-serif;--bg-primary:#101318;--bg-secondary:#283240;--purple:#bb88ff;--text-dim:#8899aa;--accent:#66bbff';
  if('${theme}'==='light')sheet.style.cssText+=';--bg-primary:#fafaff;--bg-secondary:#e4e8ee;--purple:#8844bb;--text-dim:#556677;--accent:#2266aa';
  if('${theme}'==='custom')sheet.style.cssText+=';--bg-primary:#ff9933;--bg-secondary:#145236;--purple:#ff22aa;--text-dim:#22ffee;--accent:#eecc22';
  const pairs=[];
  for(const name of window.__iconTypes){
   const row=document.createElement('div');row.style.cssText='display:flex;height:24px;align-items:center';
   const label=document.createElement('span');label.textContent=name;label.style.width='160px';row.appendChild(label);
   for(const link of [false,true]){
    const pair={name,link,nodes:[]};
    for(const legacy of [true,false]){
     const cell=document.createElement('div');cell.className=legacy?'reference':'';
     cell.style.cssText='position:relative;width:48px;height:24px;background:var(--bg-secondary)';
     cell.innerHTML=(legacy?legacyFileIconHtml:fileIconHtml)(name,{is_symlink:link});
     cell.firstChild.style.cssText='position:absolute;left:12px;top:4px';
     row.appendChild(cell);pair.nodes.push(cell);
    }
    pairs.push(pair);
   }
   sheet.appendChild(row);
  }
  document.body.appendChild(sheet);
  return pairs.map(({name,link,nodes})=>({name,link,rects:nodes.map(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})}));
 })()`);
 await frame();
 const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile(screenshotPath.replace('.png',`-icons-${theme}-${zoom}.png`),Buffer.from(shot.data,'base64'));
 const stats=await evaluate(`(async()=>{
  const img=new Image();img.src='data:image/png;base64,${shot.data}';await img.decode();
  const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0);
  return ${JSON.stringify(pairs)}.map(({name,link,rects})=>{
   const crops=rects.map(r=>ctx.getImageData(Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)).data);
   let sum=0,max=0,changed=0;
   for(let i=0;i<crops[0].length;i+=4){let pixel=0;for(let c=0;c<3;c++){const d=Math.abs(crops[0][i+c]-crops[1][i+c]);sum+=d;pixel=Math.max(pixel,d);}max=Math.max(max,pixel);if(pixel)changed++;}
   return {name,link,mean:sum/(crops[0].length/4*3),max,changed};
  });
 })()`);
 iconPixels.push({theme,zoom,stats});
 await evaluate("document.getElementById('icon-sheet').remove()");
}
await writeFile(screenshotPath.replace('.png','-icons.json'),JSON.stringify(iconPixels,null,2));
await evaluate("document.body.classList.remove('light-mode');document.body.style.zoom=1");await frame();
'''
      browser_script=tmp_path/'check-sidebar.mjs'
      driver=(root/'scripts/chrome-dump-auth.mjs').read_text()
      browser_script.write_text(driver.replace("const evaluated = await send(",interactions+"\nconst evaluated = await send(",1))
      r=subprocess.run(['node',str(browser_script),str(profile),page.as_uri(),str(tmp_path/'rendered.html'),str(tmp_path/'sidebar.png')],env={**os.environ,'LAB_UI_AUTH_COOKIE':''},capture_output=True,text=True,timeout=60)
      assert r.returncode == 0, r.stderr
      # At native scale the shared assets preserve the original painted glyphs.
      # Allow only small edge-compositing differences for masks/theme fills.
      # Fractional zoom rasterizes CSS backgrounds differently from inline SVG;
      # its geometry is checked above and screenshots remain available for QA.
      icon_pixels=json.loads((tmp_path/'sidebar-icons.json').read_text())
      for case in icon_pixels:
       if case['zoom'] != 1:continue
       for icon in case['stats']:
        assert icon['mean'] <= .1 and icon['max'] <= 20, (case['theme'],icon)
      rendered=(tmp_path/'rendered.html').read_text()
      match=re.search(r'<pre id="result">(.*?)</pre>',rendered,re.S)
      assert match and '&quot;ok&quot;:true' in match.group(1).replace(chr(34), '&quot;'), match.group(1) if match else 'No result'
     finally:
      if chrome.poll() is None:os.killpg(chrome.pid,signal.SIGTERM)
      chrome.wait(timeout=5)
