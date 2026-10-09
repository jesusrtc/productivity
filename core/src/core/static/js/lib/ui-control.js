/* The owner CLI operates a selected view through the same controls as users. */
(() => {
  'use strict';
  let bridge, socket, sequence=0, chain=Promise.resolve(), stopped=false;
  const controls='button,a[href],input:not([type=hidden]),textarea,select,[role=button],[role=menuitem],[role=menuitemradio],[role=separator],[id$=Resizer],[contenteditable=true],[draggable=true],summary';
  const visible=node=>!!node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden';
  const surface=()=>[...document.querySelectorAll('dialog[open]')].at(-1)||document;
  function find(selector) {
    if(typeof selector!=='string'||!selector)throw Error('Provide a selector from lab ui inspect.');
    const nodes=[...surface().querySelectorAll(selector)].filter(visible);
    if(nodes.length!==1)throw Error(`Selector matched ${nodes.length} visible controls. Inspect and use a unique selector.`);
    const node=nodes[0];if(node.matches(':disabled')||node.getAttribute('aria-disabled')==='true'||node.closest('[inert]'))throw Error('Control is disabled.');
    return node;
  }
  function inspect({offset=0,limit=200}={}) {
    const host=surface(),nodes=[...host.querySelectorAll(controls)].filter(visible),start=Math.max(0,Number(offset)||0),count=Math.min(1000,Math.max(1,Number(limit)||200));
    return {title:document.title,url:location.href,context:bridge.context(),total_controls:nodes.length,offset:start,
      dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({title:d.getAttribute('aria-label')||d.querySelector('h2')?.textContent||''})),
      controls:nodes.slice(start,start+count).map(node=>{
        node.dataset.labControlId ||= 'c'+(++sequence);
        const value=node.type==='password'?undefined:'value' in node?String(node.value).slice(0,2000):undefined;
        return {selector:`[data-lab-control-id="${node.dataset.labControlId}"]`,tag:node.tagName.toLowerCase(),role:node.getAttribute('role'),type:node.type||undefined,
          label:(node.getAttribute('aria-label')||node.labels?.[0]?.textContent||node.textContent||node.title||node.placeholder||'').trim().slice(0,512),
          value,checked:node.type==='checkbox'||node.type==='radio'?node.checked:undefined,disabled:!!node.disabled,draggable:node.draggable,
          href:node.getAttribute('href')||undefined,options:node.tagName==='SELECT'?[...node.options].map(o=>({value:o.value,label:o.text,selected:o.selected})):undefined};
      }),text:(host.body||host).innerText?.slice(0,12000)||''};
  }
  const point=node=>{node.scrollIntoView({block:'nearest',inline:'nearest'});const r=node.getBoundingClientRect();return{clientX:r.x+r.width/2,clientY:r.y+r.height/2};};
  const modifiers=params=>Object.fromEntries(['meta','ctrl','alt','shift'].map(key=>[key+'Key',(params.modifiers||[]).includes(key)]));
  async function perform(action,params={}) {
    if(action==='inspect')return inspect(params);
    if(bridge.actions[action])return bridge.actions[action](params);
    if(action==='wait'){
      const deadline=Date.now()+Math.min(59000,Math.max(1,Number(params.ms)||10000));
      do{const nodes=[...surface().querySelectorAll(params.selector)].filter(visible);if(params.absent?!nodes.length:nodes.some(n=>!params.text||n.textContent.includes(params.text)))return inspect();await new Promise(r=>setTimeout(r,50));}while(Date.now()<deadline);
      throw Error('Timed out waiting for control. Inspect before retrying.');
    }
    const node=params.selector?find(params.selector):document.activeElement;
    if(!node)throw Error('No focused control.');
    if(action==='click'||action==='contextmenu'){
      if(action==='click')node.focus();
      node.dispatchEvent(new MouseEvent(action,{bubbles:true,cancelable:true,button:action==='contextmenu'?2:0,...point(node),...modifiers(params)}));
    }else if(action==='hover'){
      for(let current=node;current&&current!==document.body;current=current.parentElement)current.dispatchEvent(new MouseEvent('mouseenter',{...point(node)}));
      node.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,...point(node)}));
    }else if(action==='fill'){
      if(node.readOnly)throw Error('Control is read only.');
      const value=String(params.value??'');node.focus();
      if(node.matches('input[type=checkbox],input[type=radio]'))node.checked=['true','1','yes','on'].includes(value.toLowerCase());
      else if(node.isContentEditable){const range=document.createRange();range.selectNodeContents(node);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);if(!document.execCommand('insertText',false,value))throw Error('This editor cannot be filled; use its document API.');}
      else if(node.matches('input,textarea,select')){
        const prototype=node.tagName==='SELECT'?HTMLSelectElement.prototype:node.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(prototype,'value').set.call(node,value);
      }else throw Error('Control is not editable.');
      node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));
    }else if(action==='key'){
      const key=String(params.key||''),code=params.code||({'Enter':'Enter','Escape':'Escape',' ':'Space','Tab':'Tab'}[key]||key),legacy={Enter:13,Escape:27,Tab:9,Backspace:8,Delete:46};
      const event=new KeyboardEvent('keydown',{key,code,keyCode:legacy[key]||0,which:legacy[key]||0,bubbles:true,cancelable:true,...modifiers(params)});
      node.dispatchEvent(event);
      if(!event.defaultPrevented){
        if(key==='Escape'){const modal=surface();if(modal instanceof HTMLDialogElement&&modal.dispatchEvent(new Event('cancel',{cancelable:true})))modal.close();}
        else if(key==='Enter'&&node.matches('button,a'))node.click();
        else if(key==='Enter'&&node.matches('input')&&node.form)node.form.requestSubmit();
        else if(key==='Tab'){const rows=[...surface().querySelectorAll(controls)].filter(n=>visible(n)&&!n.matches(':disabled')&&n.tabIndex>=0),index=rows.indexOf(node),step=params.modifiers?.includes('shift')?-1:1;rows[(index+step+rows.length)%rows.length]?.focus();}
      }
      node.dispatchEvent(new KeyboardEvent('keyup',{key,code,bubbles:true,...modifiers(params)}));
    }else if(action==='drag'){
      const target=find(params.target),transfer=new DataTransfer(),start=point(node),end=point(target);
      const emit=(host,type,coords)=>host.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:transfer,...coords}));
      emit(node,'dragstart',start);emit(target,'dragenter',end);emit(target,'dragover',end);emit(target,'drop',end);emit(node,'dragend',end);
    }else if(action==='pointer-drag'){
      const start=point(node),end={clientX:start.clientX+(Number(params.x)||0),clientY:start.clientY+(Number(params.y)||0)};
      for(const [host,type,coords] of [[node,'down',start],[document,'move',end],[document,'up',end]]){
        const init={bubbles:true,cancelable:true,button:0,buttons:type==='up'?0:1,...coords};
        host.dispatchEvent(new PointerEvent('pointer'+type,{pointerId:1,pointerType:'mouse',isPrimary:true,...init}));host.dispatchEvent(new MouseEvent('mouse'+type,init));
      }
    }else if(action==='scroll')node.scrollBy({top:Number(params.y)||0,left:Number(params.x)||0,behavior:'instant'});
    else throw Error('Unknown UI action.');
    for(let frame=0;frame<2;frame++)await new Promise(resolve=>{requestAnimationFrame(resolve);setTimeout(resolve,40);});
    return inspect();
  }
  async function execute(action,params={}) {
    const prompts=[],answers=[...(params.dialogs||[])],original={prompt:window.prompt,confirm:window.confirm,alert:window.alert};
    const answer=(type,message)=>{
      const next=answers[0];if(next?.type===type){answers.shift();return type==='confirm'?next.value===true:String(next.value??'');}
      prompts.push({type,message:String(message),requires_answer:type!=='alert'});return type==='confirm'?false:null;
    };
    window.prompt=message=>answer('prompt',message);window.confirm=message=>answer('confirm',message);window.alert=message=>answer('alert',message);
    let pending;
    try{pending=perform(action,params);}finally{Object.assign(window,original);}
    const result=await pending;return{...result,native_dialogs:prompts};
  }
  function info() {const context=bridge.context();return{title:document.title,url:location.href,workspace:context.workspace||'',vault:context.vault||'',visibility:document.visibilityState};}
  function publishState(){if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'state',info:info()}));}
  function connect(delay=1000) {
    if(stopped)return;
    socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/ui-control`);
    socket.onmessage=event=>{
      const message=JSON.parse(event.data);if(message.type==='connected'){publishState();return;}if(message.type!=='command')return;
      const owner=socket;
      chain=chain.catch(()=>{}).then(async()=>{
        try{const result=await execute(message.action,message.params);if(owner.readyState===WebSocket.OPEN)owner.send(JSON.stringify({type:'result',id:message.id,result}));}
        catch(error){if(owner.readyState===WebSocket.OPEN)owner.send(JSON.stringify({type:'result',id:message.id,error:error.message}));}
        publishState();
      });
    };
    socket.onclose=()=>{if(!stopped)setTimeout(()=>connect(Math.min(30000,delay*2)),delay);};
    socket.onerror=()=>{};
  }
  window.LabUiControl={start(options){if(bridge)return;bridge=options;connect();for(const event of ['focus','popstate','visibilitychange'])window.addEventListener(event,publishState);},inspect,execute};
  window.addEventListener('pagehide',()=>{stopped=true;socket?.close();});
})();
