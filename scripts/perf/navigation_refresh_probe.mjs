// Optional fixture-only call tracing; no response bodies or source contents.
export async function installNavigationRefreshProbe(evaluate,workspaceRoot) {
  if(!/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot))throw Error('Refresh tracing requires the disposable fixture');
  await evaluate(`(()=>{
    const events=[],limit=10000;let next=0;
    const state=()=>({workspace:currentWorkspace?.path,doc:_workspaceDocPath,infoSequence:_workspaceInfoSequence,sidebarSequence:_workspaceSidebarRefreshSequence});
    const record=row=>{if(events.length<limit)events.push({...row,at:performance.now(),...state()});};
    const wrap=(name,original)=>function(...args){
      const id=++next,options=args[0]||{};
      const details=name==='_sidebarFetchWorkspaceFiles'?{path:args[0]}:name==='openWorkspaceDoc'?{path:args[0],preserveScroll:!!args[1]?.preserveScroll}:name==='renderWorkspaceDoc'?{path:args[0],container:args[1]?.id||'content'}:{preserveScroll:!!options.preserveScroll,backgroundRefresh:!!options.backgroundRefresh,keepShell:!!options.keepShell,suppliedData:!!options._data,sequence:options._sequence};
      record({id,name,phase:'begin',options:details,stack:new Error().stack});
      let result;
      try{result=original.apply(this,args);}
      catch(error){record({id,name,phase:'error',error:String(error)});throw error;}
      if(result?.then)result.then(()=>record({id,name,phase:'end'}),error=>record({id,name,phase:'error',error:String(error)}));
      else record({id,name,phase:'end'});
      return result;
    };
    showWorkspaceInfo=wrap('showWorkspaceInfo',showWorkspaceInfo);
    _refreshWorkspaceSidebar=wrap('_refreshWorkspaceSidebar',_refreshWorkspaceSidebar);
    _sidebarFetchWorkspaceFiles=wrap('_sidebarFetchWorkspaceFiles',_sidebarFetchWorkspaceFiles);
    openWorkspaceDoc=wrap('openWorkspaceDoc',openWorkspaceDoc);
    renderWorkspaceDoc=wrap('renderWorkspaceDoc',renderWorkspaceDoc);
    window.__navigationRefreshProbe=()=>({events,limitReached:events.length===limit});
  })()`);
}

// Controlled overlap experiment: invoke the normal background-refresh entry
// point during each explicit navigation. Normal polling remains enabled.
// This is not a measurement of watcher/WebSocket event delivery latency.
export async function installNavigationRefreshStress(evaluate,workspaceRoot,delayMs) {
  if(!/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot))throw Error('Refresh stress requires the disposable fixture');
  if(!Number.isInteger(delayMs)||delayMs<1||delayMs>1000)throw Error('Refresh stress delay must be 1–1000 ms');
  await evaluate(`(()=>{
    const original=showWorkspaceInfo,events=[];
    showWorkspaceInfo=function(options={}){
      const result=original.apply(this,arguments);
      if(!options.backgroundRefresh && currentWorkspace?.path?.startsWith(${JSON.stringify(workspaceRoot+'/')})){
        const path=currentWorkspace?.path,root=_sidebarScopedRoot(path),sequence=_workspaceInfoSequence;
        const event={path,sequence,started:performance.now(),delivered:false};events.push(event);
        setTimeout(()=>{
          event.finished=performance.now();
          if(currentWorkspace?.path!==path||_workspaceInfoSequence!==sequence||_sidebarScopedRoot(path)!==root)return;
          event.delivered=true;
          showWorkspaceInfo({preserveScroll:true,backgroundRefresh:true});
        },${delayMs});
      }
      return result;
    };
    window.__navigationRefreshStress=()=>({delayMs:${delayMs},events});
  })()`);
}

export function navigationRefreshCoverage(rows,events,workspaceRoot) {
  return rows.filter(row=>row.kind==='workspace').map(row=>{
    const start=row.clock.source,end=start+row.ms;
    const delivered=events.filter(event=>event.path===workspaceRoot+'/'+row.target
      && event.started>=start && event.started<=end && event.delivered
      && event.finished>=event.started && event.finished<=end).length;
    return {sample:row.sample,delivered};
  });
}
