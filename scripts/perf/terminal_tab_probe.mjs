// Observe real xterm renders without changing attach, input, or cache policy.
export async function installTerminalTabProbe(evaluate, fixtures, {diagnostics=false}={}) {
  await evaluate(`(${install.toString()})(${JSON.stringify(fixtures)},${JSON.stringify(diagnostics)})`);
}

function install(fixtures, diagnostics=false) {
  const expected=new Map(fixtures.map(row=>[row.name,row.marker]));
  const records=[],tracked=new WeakMap();
  const previousStates=new WeakMap();
  const recordStage=(record,stage)=>{
    if(record.timeline.length<1000)record.timeline.push({at:performance.now(),...stage});
    else record.timelineDropped++;
  };
  const text=xt=>{
    const b=xt.buffer.active;
    let value='';
    for(let i=b.viewportY;i<=b.baseY+b.cursorY;i++)value+=b.getLine(i)?.translateToString(true,0,i===b.baseY+b.cursorY?b.cursorX:undefined)||'';
    return value;
  };
  const track=xt=>{
    if(!xt || tracked.has(xt) || !expected.has(termCurrentSession))return;
    const record={name:termCurrentSession,createdAt:performance.now(),renders:0,verified:null,renderAt:null};
    records.push(record);tracked.set(xt,record);
    if(diagnostics) {
      record.timeline=[];record.timelineDropped=0;
      xt.onWriteParsed(()=>recordStage(record,{kind:'parse',correctText:text(xt).endsWith(expected.get(record.name))}));
    }
    xt.onRender(range=>{
      record.renders++;
      const b=xt.buffer.active,cursorRow=b.baseY+b.cursorY-b.viewportY;
      if(range.start<=cursorRow && range.end>=cursorRow && text(xt).endsWith(expected.get(record.name))) {
        record.verified=expected.get(record.name);record.renderAt=performance.now();
      }
      if(diagnostics)recordStage(record,{kind:'render',start:range.start,end:range.end,cursorRow,
        correctText:text(xt).endsWith(expected.get(record.name)),verified:record.verified===expected.get(record.name)});
    });
  };
  const original=termEnsureXterm;
  termEnsureXterm=function(...args){const result=original.apply(this,args);track(termXterm);return result;};
  track(termXterm);
  const state=name=>{
    const record=tracked.get(termXterm),value=expected.get(name);
    const visible=Array.from(document.querySelectorAll('#termBody .term-pane')).filter(el=>el.getBoundingClientRect().width>0);
    const result={name,current:termCurrentSession,workspace:termCurrentWorkspaceId,
      selected:!!document.querySelector('.sess[data-name='+JSON.stringify(name)+'][aria-selected="true"]'),
      visible:visible.length,ownsVisible:visible[0]===termContainer,open:termWS?.readyState===1,
      focused:!!termXterm && document.activeElement===termXterm.element?.querySelector('textarea'),
      correctText:!!termXterm && text(termXterm).endsWith(value),
      rendered:record?.name===name&&record?.verified===value,renderAt:record?.renderAt,
      cacheSize:_termCache.size,panes:document.querySelectorAll('#termBody .term-pane').length};
    if(diagnostics&&record) {
      const key=JSON.stringify({...result,renderAt:undefined});
      if(previousStates.get(record)!==key) {
        previousStates.set(record,key);
        recordStage(record,{kind:'state',...result});
      }
    }
    return result;
  };
  window.__terminalTabs={
    state,
    addFixture(name,marker){if(expected.has(name))throw Error('Duplicate fixture terminal');expected.set(name,marker);},
    ready(name){const s=state(name);return s.current===name&&s.workspace==='alpha'&&s.selected&&s.visible===1&&s.ownsVisible&&s.open&&s.focused&&s.correctText&&s.rendered;},
    cacheState(name){const entry=_termCache.get(_termCacheKey('alpha',name));return termCurrentSession===name?'mounted':entry?(entry.ws.readyState===1?'warm':'stale'):'cold';},
    expectInput(name,key){expected.set(name,expected.get(name)+key);},
    snapshot(){return {records,expected:[...expected],state:state(termCurrentSession)};},
  };
}
