// Native shortcut/filter actions inside the disposable navigation fixture.
import {captureInputClock,validateInputClock} from './input_clock.mjs';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

export function expectedQuickFiles(files,config,query) {
  const terms=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const extensions=new Set(config.extensions||[]);
  const preferred=file=>{
    const name=file.path.split('/').at(-1),dot=name.lastIndexOf('.');
    const extension=dot>0 && dot<name.length-1?name.slice(dot+1).toLowerCase():'__none__';
    return config.trackMode!=='extensions'||extensions.has(extension);
  };
  const modified=file=>Number.isFinite(Number(file.mtime))?Number(file.mtime):0;
  return files.filter(file=>file && file.type!=='dir' && !file.broken && typeof file.path==='string' && file.path
    && terms.every(term=>file.path.toLowerCase().includes(term)))
    .sort((a,b)=>Number(preferred(b))-Number(preferred(a))||modified(b)-modified(a)||a.path.localeCompare(b.path));
}

export async function runQuickFileWorkload(client,evaluate,rows,{workspaceRoot,samples,extraFiles,fileTypes,layout}) {
  const root=workspaceRoot+'/alpha';
  if(!root.includes('/lab-navigation-')||!root.endsWith('/vault/workspaces/alpha'))throw new Error('Quick-file actions require the disposable fixture');
  const fixturePaths=Array.from({length:extraFiles},(_,i)=>'notes/'+(layout==='folders'?'batch-'+String(Math.floor(i/100)).padStart(3,'0')+'/':'')+'entry-'+String(i).padStart(5,'0')+'.'+fileTypes[i%fileTypes.length]);
  const scope=`currentWorkspace?.path===${JSON.stringify(root)} && _quickFilePicker?.scope.root===${JSON.stringify(root)} && _quickFilePicker?.scope.workspace===${JSON.stringify(root)}`;
  const ready=`${scope} && _quickFilePicker.dialog.open && !_quickFilePicker.loading && !_quickFilePicker.error && document.activeElement===_quickFilePicker.input && _quickFilePicker.list.getAttribute('aria-busy')==='false'`;
  const paths=`Array.from(document.querySelectorAll('#quickFileResults [role="option"]'),row=>row.getAttribute('title'))`;
  const selected=index=>`_quickFilePicker.selected===${index} && _quickFilePicker.input.getAttribute('aria-activedescendant')==='quickFileResult-${index}' && _quickFilePicker.list.querySelectorAll('[aria-selected="true"]').length===1 && _quickFilePicker.list.querySelector('[aria-selected="true"]')?.id==='quickFileResult-${index}'`;

  async function keyAction(kind,key,condition,{modifiers=0,text='',code=key,virtualKey=0}={}) {
    await evaluate(`(()=>{
      const captureInputClock=${captureInputClock.toString()};
      window.__quickProbe={done:false};
      window.addEventListener('keydown',event=>{
        const p=__quickProbe;
        p.clock=captureInputClock(event);p.start=p.clock.source;p.sourceEpoch=p.clock.sourceEpoch;
        p.queue=p.clock.handlerAt-event.timeStamp;
        if(event.key!==${JSON.stringify(key)}){p.error='Wrong native key';p.done=true;return;}
        const check=()=>{
          if(${condition})requestAnimationFrame(()=>setTimeout(()=>{p.ms=performance.now()-p.start;p.done=true;},0));
          else if(performance.now()-p.start>10000){p.error='Quick-file action did not finish';p.done=true;}
          else requestAnimationFrame(check);
        };requestAnimationFrame(check);
      },{once:true,capture:true});
    })()`);
    const sentEpoch=Date.now();
    await Promise.all([
      client.send('Input.dispatchKeyEvent',{type:'keyDown',timestamp:sentEpoch/1000,key,code,modifiers,windowsVirtualKeyCode:virtualKey,...(text?{text,unmodifiedText:text}:{})}),
      client.send('Input.dispatchKeyEvent',{type:'keyUp',timestamp:sentEpoch/1000,key,code,modifiers,windowsVirtualKeyCode:virtualKey}),
    ]);
    const deadline=Date.now()+12000;
    while(!await evaluate('__quickProbe.done')) {
      if(Date.now()>deadline)throw new Error('Native quick-file action timed out');
      await sleep(10);
    }
    const row=await evaluate(`({...__quickProbe,requests:performance.getEntriesByType('resource').filter(r=>r.startTime>=__quickProbe.start && r.name.includes('/api/')).map(r=>({route:new URL(r.name).pathname,start:r.startTime-__quickProbe.start,ms:r.duration}))})`);
    const clockCheck=validateInputClock(row.clock,sentEpoch);
    rows.push({sample:rows.length+1,kind,target:key,...row,sentEpoch,clockCheck});
    if(row.error||!clockCheck.valid)throw new Error('Quick-file action failed: '+JSON.stringify({row,clockCheck,state:await evaluate(`({root:currentWorkspace?.path,scope:_quickFilePicker?.scope,input:_quickFilePicker?.input.value,loading:_quickFilePicker?.loading,error:_quickFilePicker?.error,paths:${paths}})`)}));
  }

  async function open() {
    await keyAction('quick-open','k',`${ready} && !_quickFilePicker.input.value && _quickFilePicker.files.length>=${extraFiles+2} && ${selected(0)}`,{modifiers:4,code:'KeyK',virtualKey:75});
    // Validate the entire order independently after the measured render, so
    // this diagnostic sort does not add work to the measured key handler.
    const data=await evaluate(`({files:_quickFilePicker.files,config:_sidebarFileConfig,paths:${paths},status:_quickFilePicker.status.textContent})`);
    const expected=expectedQuickFiles(data.files,data.config,'');
    if(data.paths.length!==Math.min(100,expected.length)||JSON.stringify(data.paths)!==JSON.stringify(expected.slice(0,100).map(f=>f.path))||!data.status.startsWith(expected.length+' files'))throw new Error('Quick-file initial order/count is wrong');
    const returned=new Set(data.files.map(f=>f.path));
    if(!returned.has('docs/review-1.md')||!returned.has('docs/review-2.md')||fixturePaths.some(path=>!returned.has(path)))throw new Error('Quick-file fixture files are missing');
    return data;
  }

  for(let i=0;i<samples;i++) {
    const data=await open();
    let query='';
    for(const key of 'review-') {
      query+=key;
      const expected=expectedQuickFiles(data.files,data.config,query);
      const target=JSON.stringify(expected.slice(0,100).map(f=>f.path));
      await keyAction('quick-filter',key,`${ready} && _quickFilePicker.input.value===${JSON.stringify(query)} && JSON.stringify(${paths})===${JSON.stringify(target)} && ${selected(0)}`,{text:key,code:key==='-'?'Minus':'Key'+key.toUpperCase(),virtualKey:key==='-'?189:key.toUpperCase().charCodeAt(0)});
    }
    const matches=expectedQuickFiles(data.files,data.config,query);
    if(matches.length!==2)throw new Error('Review query must find exactly the two fixture documents');
    await keyAction('quick-select','ArrowDown',`${ready} && ${selected(1)}`,{virtualKey:40});
    await keyAction('quick-select','ArrowUp',`${ready} && ${selected(0)}`,{virtualKey:38});
    const path=matches[0].path,title='Alpha review '+path.match(/review-(\d+)/)[1];
    await keyAction('quick-document','Enter',`!_quickFilePicker && !document.querySelector('.quick-file-picker') && currentWorkspace?.path===${JSON.stringify(root)} && _workspaceDocRoot===${JSON.stringify(root)} && _workspaceDocPath===${JSON.stringify(path)} && document.querySelector('#content h1')?.textContent===${JSON.stringify(title)}`,{text:'\r',virtualKey:13});
    await open();
    await keyAction('quick-close','Escape',`!_quickFilePicker && !document.querySelector('.quick-file-picker') && currentWorkspace?.path===${JSON.stringify(root)} && _workspaceDocRoot===${JSON.stringify(root)} && _workspaceDocPath===${JSON.stringify(path)}`,{virtualKey:27});
  }
}
