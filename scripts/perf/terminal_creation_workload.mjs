// Native New menu/Terminal clicks with real session persistence and echo proof.
import {readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {installTerminalTabProbe} from './terminal_tab_probe.mjs';

export async function terminalCreationActions(evaluate,workspaceRoot,samples,fixture) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot)
      || !fixture?.marker?.startsWith('created-') || !fixture.shell?.startsWith(workspaceRoot.slice(0,-'/vault/workspaces'.length)+'/')) {
    throw Error('Terminal creation requires the disposable fixture');
  }
  if(!Number.isInteger(samples)||samples<2)throw Error('Terminal creation requires at least two samples');
  await installTerminalTabProbe(evaluate,[],{diagnostics:!!process.env.LAB_PERF_TRACE});
  await evaluate(`(${installCreation.toString()})(${JSON.stringify(fixture.marker)},${JSON.stringify(workspaceRoot+'/alpha')},${JSON.stringify(workspaceRoot.split('/').at(-3)+'-')})`);
  const actions=[{kind:'workspace',target:'alpha',selector:'.workspace-tab[data-workspace-id="alpha"]',
    ready:`currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/alpha')} && document.querySelector('#content [data-workspace-display-title]')?.textContent==='Alpha'`}];
  for(let i=0;i<samples;i++)actions.push(
    {kind:'terminal-create-picker',target:i+1,selector:'#termNewBtn',ready:`document.getElementById('termNewPicker')?.classList.contains('open') && !document.querySelector('#termNewPicker [data-term-option="terminal"]').disabled`},
    {kind:'terminal-create',target:i+1,selector:'#termNewPicker [data-term-option="terminal"]',ready:`__terminalCreation.ready(${i+1})`},
  );
  return actions;
}

function installCreation(marker,scope,prefix) {
  const names=[];
  const original=termAttach;
  termAttach=function(name,...args) {
    if(!name.startsWith(prefix) || currentWorkspace?.path!==scope)throw Error('Terminal creation escaped fixture scope');
    if(!names.includes(name)) {
      names.push(name);
      __terminalTabs.addFixture(name,marker);
    }
    return original.call(this,name,...args);
  };
  window.__terminalCreation={
    ready(count){
      const name=names[count-1],rows=document.querySelectorAll('#termSessionList .sess[data-name]');
      return names.length===count && rows.length===count && termSessions.length===count
        && termSessions.every(s=>s.kind==='terminal'&&s.workspace_id==='alpha')
        && !document.getElementById('termNewPicker')?.classList.contains('open')
        && __terminalTabs.ready(name);
    },
    snapshot(){return {names:[...names],sessions:termSessions.map(s=>({name:s.name,logical_name:s.logical_name,kind:s.kind})),terminal:__terminalTabs.snapshot()};},
  };
}

export async function verifyTerminalCreation(client,evaluate,workspaceRoot,count) {
  const initial=await evaluate('__terminalCreation.snapshot()'),name=initial.names[count-1];
  if(initial.names.length!==count || new Set(initial.names).size!==count)throw Error('Creation reused a live terminal');
  const key=String.fromCharCode(97+(count-1)%26);
  await evaluate(`__terminalTabs.expectInput(${JSON.stringify(name)},${JSON.stringify(key)})`);
  await client.send('Input.dispatchKeyEvent',{type:'keyDown',key,code:'Key'+key.toUpperCase(),text:key,unmodifiedText:key,windowsVirtualKeyCode:key.toUpperCase().charCodeAt(0)});
  await client.send('Input.dispatchKeyEvent',{type:'keyUp',key,code:'Key'+key.toUpperCase(),windowsVirtualKeyCode:key.toUpperCase().charCodeAt(0)});
  const deadline=Date.now()+10000;
  while(!await evaluate(`__terminalCreation.ready(${count})`)) {
    if(Date.now()>deadline)throw Error('Created terminal did not render exact native input');
    await new Promise(resolve=>setTimeout(resolve,10));
  }
  const metadata=JSON.parse(await readFile(join(workspaceRoot,'alpha','workspace.json'),'utf8'));
  const beta=JSON.parse(await readFile(join(workspaceRoot,'beta','workspace.json'),'utf8'));
  const state=await evaluate('__terminalCreation.snapshot()');
  if(state.terminal.state.cacheSize>3 || state.terminal.state.panes>4)throw Error('Terminal creation exceeded pane retention bounds');
  const saved=metadata.sessions||[];
  if(saved.length!==count || new Set(saved.map(s=>s.name)).size!==count
      || new Set(state.sessions.map(s=>s.logical_name)).size!==count
      || (beta.sessions||[]).length || state.sessions.length!==count
      || state.sessions.some(row=>!saved.some(s=>s.name===row.logical_name&&s.kind==='terminal')))
    throw Error('Created terminals were not persisted in their owning workspace');
  return {name,key,state,savedCount:saved.length,otherWorkspaceCount:(beta.sessions||[]).length};
}
