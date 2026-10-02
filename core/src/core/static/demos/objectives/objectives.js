(() => {
      const root = document.getElementById('lab-objectives-proposal');
      const find = name => root.querySelector('[data-' + name + ']');
      const channel = 'lab-objectives-demo-v1';
      let hydrated = false;
      const iconNames = {document:'file-text',assistant:'files',notebook:'notebook',link:'external-link',task:'square-check',file:'file-code',folder:'folder'};
      const objectives = [
        {id:'sms',name:'SMS recovery',purpose:'Restore reliable phone verification',color:'#58a6ff',selected:'phone-fix',selectedItem:'incident',draft:'',worktrees:[{id:'phone-fix',name:'sdui/fix-phone',repo:'client',color:'#58a6ff'},{id:'checkpoint',name:'checkpoint/verification',repo:'client',color:'#ff7b72'}],items:[
          {id:'incident',kind:'document',title:'Incident notes',scope:null,body:'Investigate failed phone verification and record the recovery plan.'},
          {id:'track',kind:'assistant',title:'Investigation — Track 3',scope:null,body:'Linked Assistant document. Its existing content and tasks remain owned by Assistant.'},
          {id:'volume',kind:'notebook',title:'Verification volume.ipynb',scope:null},
          {id:'thread',kind:'link',title:'Malformed-phone discussion',scope:null,url:'https://example.com/discussion'},
          {id:'channel',kind:'link',title:'Incident channel',scope:null,url:'https://example.com/channel'},
          {id:'ticket',kind:'link',title:'Ticket — Unparseable phone',scope:null,url:'https://example.com/ticket'},
          {id:'validate',kind:'task',title:'Validate phone parsing',scope:null,checks:[{title:'Reproduce malformed input',done:true},{title:'Verify recovery behavior',done:false},{title:'Record regression coverage',done:false}],detail:'incident'},
          {id:'rollout',kind:'task',title:'Review rollout results',scope:null,checks:[{title:'Compare verification rates',done:false}],detail:'volume'},
          {id:'prs',kind:'link',title:'PRs for this branch',scope:'phone-fix',url:'https://example.com/pull-requests'}],recent:['api/phone_parser.py','tests/test_phone_parser.py'],files:['api/','applications/','build/','client/']},
        {id:'api',name:'API cleanup',purpose:'Simplify the public API',color:'#bc8cff',selected:'api-main',selectedItem:'api-plan',draft:'',worktrees:[{id:'api-main',name:'cleanup/routes',repo:'service',color:'#bc8cff'},{id:'api-tests',name:'cleanup/contract-tests',repo:'service',color:'#e3b341'}],items:[{id:'api-plan',kind:'document',title:'API cleanup plan',scope:null,body:'Review route behavior, remove redundant paths, and document the supported API.'},{id:'api-reference',kind:'link',title:'API reference',scope:null,url:'https://example.com/api'},{id:'api-task',kind:'task',title:'Review compatibility',scope:null,checks:[{title:'List existing consumers',done:true},{title:'Verify current contracts',done:false}],detail:'api-plan'}],recent:['service/routes.py','tests/test_contracts.py'],files:['service/','tests/','README.md']},
        {id:'latency',name:'Latency study',purpose:'Understand response time',color:'#ffa657',selected:'timing',selectedItem:'measurements',draft:'',worktrees:[{id:'timing',name:'perf/timing',repo:'service',color:'#ffa657'}],items:[{id:'measurements',kind:'notebook',title:'Measurements.ipynb',scope:null},{id:'latency-task',kind:'task',title:'Compare response times',scope:null,checks:[{title:'Capture a baseline',done:true},{title:'Repeat the measurements',done:false}],detail:'measurements'}],recent:['scripts/benchmark.py'],files:['scripts/','results/']},
        {id:'docs',name:'Documentation',purpose:'Improve onboarding',color:'#39c5cf',selected:'docs-main',selectedItem:'onboarding',draft:'',worktrees:[{id:'docs-main',name:'docs/onboarding',repo:'client',color:'#39c5cf'}],items:[{id:'onboarding',kind:'document',title:'Onboarding guide',scope:null,body:'Document the setup and first useful workflow.'}],recent:['docs/setup.md'],files:['docs/','README.md']}
      ];
      const terminals = [{id:'t1',objective:'sms',tree:'phone-fix',name:'Parsing fix',linked:'validate',state:'working',draft:''},{id:'t2',objective:'sms',tree:'phone-fix',name:'Test runner',linked:null,state:'ready',draft:''},{id:'t3',objective:'sms',tree:'checkpoint',name:'Investigation',linked:'incident',state:'idle',draft:''},{id:'t4',objective:'api',tree:'api-main',name:'Route review',linked:'api-plan',state:'working',draft:''},{id:'t5',objective:'api',tree:'api-tests',name:'Contract tests',linked:null,state:'idle',draft:''},{id:'t6',objective:'latency',tree:'timing',name:'Benchmark',linked:'measurements',state:'ready',draft:''},{id:'t7',objective:'docs',tree:'docs-main',name:'Guide edits',linked:'onboarding',state:'idle',draft:''}];
      const config = {groupResources:false,terminalVisibility:'all'};
      let focused = ['sms','api','latency'], selected = 'sms', activeTerminal = 't1', serial = 10, recentMode = 'Uncommitted';
      const openFolders = new Set();
      const palettes = [['#58a6ff','#ff7b72','#3fb950','#d29922'],['#bc8cff','#e3b341','#56d6c0','#ff9bce'],['#ffa657','#f778ba','#a9d14c','#b3a456'],['#39c5cf','#e86b8d','#d1bcff','#acd68f']];
      objectives.forEach((o,index)=>{
        o.palette=palettes[index];
        o.worktrees.forEach(tree=>seedFiles(o,tree));
        o.items.filter(i=>i.kind==='notebook').forEach(i=>{i.source='rates = [0.96, 0.98, 0.99]\nmean_rate = sum(rates) / len(rates)\nprint(f"Mean verification rate: {mean_rate:.1%}")';i.output='Mean verification rate: 97.7%';});
      });
      terminals.forEach(t=>t.logs=['Objectives demo terminal · help lists simulated commands.']);
      const fresh = JSON.parse(JSON.stringify(snapshot()));

      function snapshot() {return {version:1,objectives,terminals,config,focused,selected,activeTerminal,serial,recentMode,openFolders:[...openFolders]};}
      function persist() {if(hydrated&&window.parent!==window)window.parent.postMessage({channel,type:'save',state:snapshot()},'*');}
      function seedFiles(o,tree) {
        const paths=[...new Set([...o.recent,'README.md',tree.repo==='client'?'api/phone_parser.py':'service/routes.py',tree.repo==='client'?'tests/test_phone_parser.py':'tests/test_contracts.py'])];
        paths.forEach((path,index)=>o.items.push({id:'file-'+tree.id+'-'+index,kind:'file',title:path,scope:tree.id,listed:false,body:path.endsWith('.md')?'# '+o.name+'\n\nNotes for '+tree.name+'.':path.endsWith('.py')?'# Simulated file in '+tree.name+'\n\ndef verify(value):\n    return bool(value)\n':'Simulated file content.',updated:Date.now()}));
      }
      function validState(state) {
        if(state?.version!==1||!Array.isArray(state.objectives)||!state.objectives.length||state.objectives.length>100||!Array.isArray(state.terminals)||!Array.isArray(state.focused)||state.focused.length>3||!state.focused.length)return false;
        const ids=new Set();
        for(const o of state.objectives){
          if(typeof o.id!=='string'||ids.has(o.id)||typeof o.name!=='string'||typeof o.color!=='string'||!Array.isArray(o.worktrees)||!Array.isArray(o.items)||!Array.isArray(o.files)||!Array.isArray(o.recent))return false;
          ids.add(o.id);const treeIds=new Set(o.worktrees.map(t=>t.id));
          if(o.worktrees.some(t=>typeof t.name!=='string'||typeof t.color!=='string'||typeof t.repo!=='string')||o.selected&&!treeIds.has(o.selected))return false;
          if(o.items.some(i=>typeof i.id!=='string'||typeof i.title!=='string'||!Object.hasOwn(iconNames,i.kind)||i.scope&&!treeIds.has(i.scope)||i.kind==='task'&&(!Array.isArray(i.checks)||i.checks.some(c=>typeof c.title!=='string'||typeof c.done!=='boolean'))))return false;
        }
        if(new Set(state.focused).size!==state.focused.length||state.focused.some(id=>!ids.has(id))||!state.focused.includes(state.selected))return false;
        return state.terminals.every(t=>typeof t.id==='string'&&typeof t.name==='string'&&state.objectives.some(o=>o.id===t.objective&&(t.tree==='objective'||o.worktrees.some(tree=>tree.id===t.tree))));
      }
      function restore(state) {if(!validState(state))return false;objectives.splice(0,objectives.length,...state.objectives);terminals.splice(0,terminals.length,...state.terminals);config.groupResources=state.config?.groupResources===true;config.terminalVisibility=state.config?.terminalVisibility==='selected'?'selected':'all';focused=[...state.focused];selected=state.selected;activeTerminal=state.activeTerminal;serial=Number.isSafeInteger(state.serial)?state.serial:100;recentMode=state.recentMode||'Uncommitted';openFolders.clear();(state.openFolders||[]).forEach(id=>openFolders.add(id));return true;}
      window.addEventListener('message',event=>{if(event.source!==window.parent||event.data?.channel!==channel||event.data.type!=='hydrate'||hydrated)return;restore(event.data.state);hydrated=true;render();});
      const objective = () => objectives.find(item => item.id === selected);
      function element(tag, className, content) { const el=document.createElement(tag); if(className) el.className=className; if(content!==undefined) el.textContent=content; return el; }
      function icon(name) { const el=element('span','ob-icon',({'target':'◎','git-branch':'⑂','file-text':'▤','files':'▥','notebook':'▦','terminal':'›_','external-link':'↗','square-check':'☑','file-code':'◇','folder':'▸'})[name]||'◇');el.setAttribute('aria-hidden','true');return el; }
      function button(label, className, action) { const el=element('button',className,label); el.type='button'; el.onclick=action; return el; }
      function message(text) { find('message').textContent=text; }
      function refreshIcons() {}
      function todoCount(o) { return o.items.filter(i=>i.kind==='task').reduce((n,i)=>n+i.checks.filter(c=>!c.done).length,0); }
      function switchObjective(id) { selected=id; const o=objective(); const t=terminals.find(t=>t.objective===id&&t.tree===o.selected)||terminals.find(t=>t.objective===id); activeTerminal=t?t.id:null; find('dialog').hidden=true; render(); message(o.name+' · '+todoCount(o)+' open to-dos · '+o.worktrees.length+' associated worktrees'); }
      function attachDrop(el, type, action) {
        el.ondragover=e=>{if(e.dataTransfer.types.includes(type)){e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='link';el.classList.add('ob-drop');}};
        el.ondragleave=()=>el.classList.remove('ob-drop');
        el.ondrop=e=>{el.classList.remove('ob-drop');const id=e.dataTransfer.getData(type);if(id){e.preventDefault();e.stopPropagation();action(id);}};
      }
      function renderFocus() {
        const host=find('focus'); host.replaceChildren();
        focused.forEach(id=>{const o=objectives.find(o=>o.id===id);const b=button('', 'ob-focus-slot',()=>switchObjective(id));b.style.setProperty('--objective-color',o.color);b.setAttribute('aria-pressed',id===selected);b.append(icon('target'));const label=element('span','ob-focus-name',o.name);label.append(element('span','',todoCount(o)+' to-dos'));b.append(label);host.append(b);});
        const add=button('+','ob-action',focusDialog);add.setAttribute('aria-label','Choose another objective');host.append(add);
      }
      function heading(host,label,action) {const row=element('div','ob-section-heading');row.append(element('span','',label));if(action){const add=button('+','ob-quiet',action);add.setAttribute('aria-label','Add to '+label.toLowerCase());row.append(add);}host.append(row);}
      function resourceRow(item,o) {
        const row=button('','ob-resource',()=>{o.selectedItem=item.id;renderReader();renderOverview();persist();});row.dataset.item=item.id;row.dataset.selected=o.selectedItem===item.id;row.draggable=true;row.setAttribute('aria-label',item.title+' · '+item.kind);row.title='Drag onto a worktree to limit visibility';
        row.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-item',item.id);e.dataTransfer.effectAllowed='link';};row.ondragend=()=>root.querySelectorAll('.ob-drop').forEach(el=>el.classList.remove('ob-drop'));
        row.append(icon(iconNames[item.kind]||'file-text'),element('span','ob-label',item.title));
        if(item.kind==='task') {const done=item.checks.filter(c=>c.done).length;row.append(element('span','ob-progress',done+'/'+item.checks.length+' done'));}
        else if(item.kind==='assistant')row.append(element('span','ob-kind','Assistant'));
        attachDrop(row,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id);if(t&&t.objective===o.id){t.linked=item.id;render();message('Linked '+t.name+' to '+item.title+' · launch folder kept');}else{message('Choose a terminal in '+o.name+' to link this resource');}});
        if(item.kind!=='task')return row;
        const wrapper=element('div','ob-task-item'),check=element('input');check.type='checkbox';check.checked=item.checks.every(c=>c.done);check.setAttribute('aria-label','Complete '+item.title);check.onchange=()=>{item.checks.forEach(c=>c.done=check.checked);render();};wrapper.append(check,row);return wrapper;
      }
      function listResources(host,items,o) {const list=element('div','ob-list');items.forEach(item=>list.append(resourceRow(item,o)));host.append(list);}
      function renderOverview() {
        const host=find('overview'),o=objective();host.replaceChildren();
        const overviewHeader=element('div','ob-section-heading');overviewHeader.append(element('span','',o.name.toUpperCase()),button('Settings','ob-quiet',settingsDialog));host.append(overviewHeader);
        const shared=element('section');shared.setAttribute('aria-label','Objective-wide resources');attachDrop(shared,'application/x-objective-item',id=>{const item=o.items.find(i=>i.id===id);if(item){item.scope=null;render();message(item.title+' now appears across '+o.name);}});
        const general=o.items.filter(i=>!i.scope&&i.kind!=='task'&&i.listed!==false);
        if(config.groupResources){heading(shared,'DOCUMENTS & LINKS',()=>itemDialog());listResources(shared,general,o);}
        else {heading(shared,'DOCUMENTS & NOTEBOOKS',()=>itemDialog('document'));listResources(shared,general.filter(i=>i.kind!=='link'),o);heading(shared,'LINKS',()=>itemDialog('link'));listResources(shared,general.filter(i=>i.kind==='link'),o);}
        heading(shared,'TASKS · '+todoCount(o)+' OPEN TO-DOS',()=>itemDialog('task'));listResources(shared,o.items.filter(i=>i.kind==='task'&&!i.scope),o);host.append(shared);
        heading(host,'WORKTREES',worktreeDialog);const trees=element('div','ob-list');
        o.worktrees.forEach(tree=>{const b=button('','ob-worktree',()=>{o.selected=tree.id;render();message(tree.name+' selected · objective resources remain visible');});b.style.setProperty('--tree-color',tree.color);b.setAttribute('aria-pressed',tree.id===o.selected);b.setAttribute('aria-label','Select worktree '+tree.name);b.append(icon('git-branch'),element('span','ob-label',tree.name),element('span','ob-kind',tree.repo));attachDrop(b,'application/x-objective-item',id=>{const item=o.items.find(i=>i.id===id);if(item){item.scope=tree.id;o.selected=tree.id;render();message(item.title+' now appears only when '+tree.name+' is selected');}});trees.append(b);});host.append(trees);
        const scoped=o.items.filter(i=>i.scope===o.selected&&i.listed!==false);if(scoped.length){heading(host,'FOR THIS WORKTREE',()=>itemDialog('link',o.selected));listResources(host,scoped,o);}
        heading(host,'RECENTLY UPDATED');const filters=element('div','ob-filters');['15 min','1 hour','24 hours','Uncommitted','vs main'].forEach(mode=>{const b=button(mode,'',()=>{recentMode=mode;renderOverview();persist();});b.setAttribute('aria-pressed',mode===recentMode);filters.append(b);});host.append(filters);
        const tree=o.worktrees.find(t=>t.id===o.selected);if(!tree){host.append(element('div','ob-muted','Associate a worktree to browse its files.'));return;}
        const files=o.items.filter(i=>i.scope===tree.id&&i.listed===false);const recent=files.filter(i=>i.updated).sort((a,b)=>b.updated-a.updated).slice(0,recentMode==='vs main'?2:recentMode==='15 min'?1:4);
        recent.forEach(item=>host.append(fileButton(item.title,o,tree)));
        heading(host,'FILES · '+tree.name,()=>itemDialog('file',tree.id));
        const folders=[...new Set(files.filter(i=>i.title.includes('/')).map(i=>i.title.split('/')[0]+'/'))].sort();
        folders.forEach(folder=>{const id=o.id+'/'+tree.id+'/'+folder;const b=button('','ob-file',()=>{if(openFolders.has(id))openFolders.delete(id);else openFolders.add(id);renderOverview();persist();});b.setAttribute('aria-expanded',openFolders.has(id));b.setAttribute('aria-label','Folder '+folder);b.append(icon('folder'),element('span','',folder));host.append(b);if(openFolders.has(id))files.filter(i=>i.title.startsWith(folder)).forEach(i=>{const file=fileButton(i.title,o,tree);file.classList.add('ob-file-child');host.append(file);});});
        files.filter(i=>!i.title.includes('/')).forEach(i=>host.append(fileButton(i.title,o,tree)));
      }
      function fileButton(path,o,tree) {
        const getItem=()=>o.items.find(i=>i.title===path&&i.scope===tree.id&&i.listed===false);
        const b=button('','ob-file',()=>{o.selectedItem=getItem().id;renderReader();persist();});b.append(icon(path.endsWith('/')?'folder':'file-code'),element('span','',path));b.title=tree.repo+' / '+tree.name+' / '+path;
        b.draggable=true;b.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-item',getItem().id);e.dataTransfer.effectAllowed='link';};
        attachDrop(b,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id);if(t&&t.objective===o.id){t.linked=getItem().id;render();message('Linked '+t.name+' to '+path+' · launch folder kept');}else message('Choose a terminal in '+o.name+' to link this file');});return b;
      }
      function renderReader() {
        const host=find('reader'),o=objective();const item=o.items.find(i=>i.id===o.selectedItem)||o.items[0];host.replaceChildren();if(!item){host.append(element('p','ob-muted','Choose or create a document, notebook, link, or task.'));return;}
        const top=element('div','ob-reader-head');top.append(element('h2','',item.title));top.append(button('Rename','ob-quiet',()=>renameDialog(item)));host.append(top);
        host.append(element('div','ob-muted',o.name+' / '+(item.scope?o.worktrees.find(t=>t.id===item.scope).name:'Objective')));
        if(item.listed!==false){const visibility=element('label','ob-visibility','Visible in '),selector=element('select');selector.setAttribute('aria-label','Resource visibility');[{id:'',name:'Whole objective'},...o.worktrees].forEach(t=>{const opt=element('option','',t.name);opt.value=t.id;selector.append(opt);});selector.value=item.scope||'';selector.onchange=()=>{item.scope=selector.value||null;render();message(item.scope?'Resource scoped to the selected worktree':'Resource visible throughout the objective');};visibility.append(selector);host.append(visibility);}
        if(item.kind==='task') {
          const done=item.checks.filter(c=>c.done).length;host.append(element('p','',done+' of '+item.checks.length+' to-dos complete'));
          const checks=element('div','ob-checklist');item.checks.forEach(c=>{const label=element('label'),input=element('input');input.type='checkbox';input.checked=c.done;input.onchange=()=>{c.done=input.checked;render();};label.append(input,element('span','',c.title));checks.append(label);});host.append(checks);
          const detail=o.items.find(i=>i.id===item.detail);if(detail){host.append(element('h3','','Details'));host.append(button(detail.title,'ob-resource',()=>{o.selectedItem=detail.id;render();}));}
          const actions=element('div','ob-reader-actions');actions.append(button('+ To-do','ob-action',()=>todoDialog(item)),button('Link details document','ob-action',()=>detailDialog(item)));host.append(actions);
        } else if(item.kind==='notebook') {
          const cell=element('div','ob-cell');cell.append(element('div','ob-muted','Python · simulated cell'));const code=element('textarea','ob-editor ob-code');code.setAttribute('aria-label','Notebook cell code');code.value=item.source||'';code.oninput=()=>{item.source=code.value;persist();};cell.append(code,button('Run simulated cell','ob-action',()=>{item.output=simulateCell(item.source||'');renderReader();persist();}));if(item.output)cell.append(element('pre','ob-output',item.output));host.append(cell);
        } else if(item.kind==='link') {host.append(element('p','',item.title),element('p','ob-muted',item.url),element('p','ob-muted','External link preview'));}
        else {host.append(element('p','',item.body||''));if(item.id==='incident'){host.append(element('h3','','Current work'));const ul=element('ul');['Reproduce the input that fails phone parsing.','Verify that recovery remains available.','Compare verification volume after the change.'].forEach(text=>ul.append(element('li','',text)));host.append(ul);const task=o.items.find(i=>i.id==='validate');host.append(element('h3','','Related task'),button('Validate phone parsing · '+task.checks.filter(c=>c.done).length+'/3 done','ob-resource',()=>{o.selectedItem='validate';render();}));}}
        const linked=terminals.filter(t=>t.objective===o.id&&t.linked===item.id);if(linked.length){host.append(element('h3','','Linked terminals'));linked.forEach(t=>host.append(button(t.name,'ob-resource',()=>selectTerminal(t))));}
        if(item.kind==='document'||item.kind==='file'){const editor=element('textarea','ob-editor');editor.setAttribute('aria-label','Edit simulated file content');editor.value=item.body||'';editor.oninput=()=>{item.body=editor.value;item.updated=Date.now();persist();};host.append(element('h3','','Edit content'),editor);}
        const actions=element('div','ob-reader-actions');actions.append(button('Link terminal','ob-action',()=>linkTerminalDialog(item)),button('Delete item','ob-quiet',()=>deleteDialog(item)));host.append(actions);
      }
      function selectTerminal(t) {selected=t.objective;const o=objective();if(t.tree!=='objective')o.selected=t.tree;if(t.linked&&o.items.some(i=>i.id===t.linked))o.selectedItem=t.linked;activeTerminal=t.id;render();message(t.name+' · '+(t.tree==='objective'?'Objective folder':o.worktrees.find(tree=>tree.id===t.tree).name));}
      function renderTerminals() {
        const host=find('terminals');host.replaceChildren();const head=element('div','ob-terminal-heading');head.append(element('strong','','Terminals'));const mode=element('select');mode.setAttribute('aria-label','Visible terminal groups');[['all','3 objectives'],['selected','Selected objective']].forEach(([value,label])=>{const opt=element('option','',label);opt.value=value;mode.append(opt);});mode.value=config.terminalVisibility;mode.onchange=()=>{config.terminalVisibility=mode.value;renderTerminals();persist();};head.append(mode);host.append(head);const surface=element('div','ob-terminal-surface'),rail=element('div','ob-terminal-groups');surface.append(rail);host.append(surface);
        focused.filter(id=>config.terminalVisibility==='all'||id===selected).forEach(id=>{const o=objectives.find(o=>o.id===id);const heading=element('div','ob-terminal-objective');heading.style.setProperty('--objective-color',o.color);heading.append(icon('target'),button(o.name,'',()=>switchObjective(id)));rail.append(heading);
          [{id:'objective',name:'Objective folder',color:o.color},...o.worktrees].forEach(tree=>{const group=terminals.filter(t=>t.objective===id&&t.tree===tree.id);if(!group.length)return;const label=element('div','ob-terminal-tree');label.style.setProperty('--tree-color',tree.color);label.append(element('span','ob-tree-dot'),element('span','',tree.name));rail.append(label);
            group.forEach(t=>{const item=o.items.find(i=>i.id===t.linked);const b=button('','ob-terminal',()=>selectTerminal(t));b.style.setProperty('--tree-color',tree.color);b.setAttribute('aria-pressed',t.id===activeTerminal);b.draggable=true;b.setAttribute('aria-label',t.name+' terminal'+(item?' linked to '+item.title:''));b.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-terminal',t.id);e.dataTransfer.effectAllowed='link';};b.ondragend=()=>root.querySelectorAll('.ob-drop').forEach(el=>el.classList.remove('ob-drop'));attachDrop(b,'application/x-objective-item',itemId=>{const target=o.items.find(i=>i.id===itemId);if(target){t.linked=itemId;render();message('Linked '+t.name+' to '+target.title+' · launch folder kept');}else message('Choose an item from '+o.name);});b.append(icon(item?(iconNames[item.kind]||'terminal'):'terminal'),element('span','ob-label',item?item.title:t.name));if(t.state!=='idle'){const dot=element('span','ob-status-dot'+(t.state==='ready'?' ready':''));dot.setAttribute('aria-label',t.state==='ready'?'Ready to review':'Working');b.append(dot);}rail.append(b);});
          });
        });
        rail.append(button('+ Terminal','ob-action ob-new-terminal',terminalDialog));const t=terminals.find(t=>t.id===activeTerminal);if(t){const console=element('div','ob-console');const folder=t.tree==='objective'?'objectives/'+t.objective:objectives.find(o=>o.id===t.objective).worktrees.find(tree=>tree.id===t.tree).name;console.append(element('strong','',t.name),element('p','ob-muted','/demo/'+folder));const logs=element('pre','ob-console-log',(t.logs||[]).join('\n\n'));console.append(logs);const label=element('label','','Command or prompt'),draft=element('textarea','ob-editor');draft.value=t.draft;draft.setAttribute('aria-label','Unsent prompt for '+t.name);draft.oninput=()=>{t.draft=draft.value;persist();};label.append(draft);console.append(label,button('Run simulation','ob-action',()=>runCommand(t)),element('div','ob-console-note','Try pwd, ls, cat README.md, echo hello, or help.'));if(t.linked)console.append(button('Unlink item','ob-quiet',()=>{t.linked=null;render();}));surface.append(console);}
      }
      function dialog(title) {const host=find('dialog');host.hidden=false;host.replaceChildren(element('h3','',title));const form=element('form');host.append(form);form.append(button('Cancel','ob-quiet',()=>{host.hidden=true;}));return form;}
      function field(form,labelText,control) {const label=element('label','',labelText);control.setAttribute('aria-label',labelText);label.append(control);form.insertBefore(label,form.lastChild);return control;}
      function select(options) {const el=element('select');options.forEach(o=>{const opt=element('option','',o.name);opt.value=o.id;el.append(opt);});return el;}
      function submit(form,label,action) {const b=button(label,'ob-action');b.type='submit';form.insertBefore(b,form.lastChild);form.onsubmit=e=>{e.preventDefault();action();find('dialog').hidden=true;render();};}
      function focusDialog() {
        const available=objectives.filter(o=>!focused.includes(o.id));const form=dialog('Bring an objective into focus');const pick=field(form,'Objective',select([...available,{id:'__new',name:'Create a new objective…'}]));const name=field(form,'New objective name',element('input'));name.type='text';name.parentElement.hidden=true;pick.onchange=()=>{name.parentElement.hidden=pick.value!=='__new';name.required=pick.value==='__new';};const slot=field(form,'Replace focus slot',select(focused.map((id,index)=>({id:String(index),name:objectives.find(o=>o.id===id).name}))));submit(form,'Replace',()=>{const old=focused[Number(slot.value)];let o=objectives.find(o=>o.id===pick.value);if(pick.value==='__new'){o={id:'objective-'+serial++,name:name.value.trim(),purpose:'',color:nextColor(),selected:null,selectedItem:null,draft:'',worktrees:[],items:[],recent:[],files:[]};objectives.push(o);}if(o){focused[Number(slot.value)]=o.id;selected=o.id;activeTerminal=terminals.find(t=>t.objective===o.id)?.id||null;message(o.name+' is in focus · '+objectives.find(o=>o.id===old).name+' sessions keep running');}});
      }
      function itemDialog(kind='document',scope=null) {
        const form=dialog(kind==='file'?'Create a simulated worktree file':'Add an objective resource');const kinds=kind==='file'?['file','notebook','document']:['document','notebook','task','link','assistant'];const type=field(form,'Type',select(kinds.map(id=>({id,name:id==='assistant'?'Assistant document reference':id[0].toUpperCase()+id.slice(1)}))));type.value=kind;const input=field(form,'Name',element('input'));input.type='text';input.required=true;if(kind==='file')input.placeholder='notes/findings.md';const url=field(form,'URL for a link',element('input'));url.type='text';url.parentElement.hidden=kind!=='link';type.onchange=()=>{url.parentElement.hidden=type.value!=='link';};
        submit(form,'Create',()=>{const o=objective(),k=type.value;let title=input.value.trim();if(k==='notebook'&&!title.endsWith('.ipynb'))title+='.ipynb';const item={id:'item-'+serial++,kind:k,title,scope,body:k==='assistant'?'Simulated reference to an existing Assistant document.':'',source:'',url:url.value,listed:kind==='file'?false:true,updated:Date.now(),checks:k==='task'?[{title,done:false}]:undefined};o.items.push(item);o.selectedItem=item.id;message('Created '+title+' in '+o.name+' · demo data');});
      }
      function renameDialog(item) {const form=dialog('Rename '+item.kind),input=field(form,'Name',element('input'));input.type='text';input.value=item.title;input.required=true;submit(form,'Rename',()=>{item.title=input.value.trim();if(item.kind==='notebook'&&!item.title.endsWith('.ipynb'))item.title+='.ipynb';message('Renamed resource · its links remain intact');});}
      function nextColor(o=null) {
        const used=new Set(objectives.flatMap(o=>o.worktrees.map(t=>t.color)));const reserved=new Set(objectives.flatMap(o=>[o.color,...(o.palette||[])]));
        const own=o?.palette?.find(c=>!used.has(c));if(own)return own;
        const extra=['#79c0ff','#da9dff','#8ddb8c','#ffad80'].find(c=>!used.has(c)&&!reserved.has(c));return extra||'hsl('+((serial*137.508)%360)+' 66% 65%)';
      }
      function worktreeDialog() {
        const form=dialog('Associate a worktree');const action=field(form,'Action',select([{id:'existing',name:'Bring an existing worktree'},{id:'new',name:'Create a new worktree'}]));const repo=field(form,'Repository',select([{id:'client',name:'client'},{id:'service',name:'service'}]));const existing=field(form,'Existing worktree',select([{id:'feature/retry',name:'feature/retry'},{id:'feature/analytics',name:'feature/analytics'},{id:'main',name:'main'}]));const name=field(form,'New branch name',element('input'));name.type='text';name.value='fix/follow-up';name.parentElement.hidden=true;action.onchange=()=>{name.parentElement.hidden=action.value!=='new';name.required=action.value==='new';existing.parentElement.hidden=action.value==='new';};
        submit(form,'Associate',()=>{const o=objective(),title=action.value==='new'?name.value.trim():existing.value;const duplicate=objectives.find(p=>p.worktrees.some(t=>t.name===title&&t.repo===repo.value));if(duplicate){message(title+' is already associated with '+duplicate.name);return;}const tree={id:'tree-'+serial++,name:title,repo:repo.value,color:nextColor(o)};o.worktrees.push(tree);seedFiles(o,tree);o.selected=tree.id;message((action.value==='new'?'Created':'Associated')+' '+tree.name+' with '+o.name+' · demo data');});
      }
      function terminalDialog() {const o=objective(),form=dialog('New terminal · '+o.name),scope=field(form,'Launch folder',select([{id:'objective',name:'Objective folder'},...o.worktrees]));scope.value=o.selected||'objective';submit(form,'Open terminal',()=>{const id='terminal-'+serial++,tree=scope.value;const t={id,objective:o.id,tree,name:'Terminal '+serial,linked:null,state:'idle',draft:'',logs:['New simulated session. Type help to explore.']};terminals.push(t);activeTerminal=id;message('Opened simulated terminal · launch folder remains fixed');});}
      function settingsDialog() {const form=dialog('Objective settings'),o=objective(),input=field(form,'Objective name',element('input'));input.type='text';input.value=o.name;input.required=true;const goal=field(form,'Outcome',element('input'));goal.type='text';goal.value=o.purpose||'';const grouping=field(form,'Resource sections',select([{id:'separate',name:'Documents / Links / Tasks'},{id:'combined',name:'Documents & links / Tasks'}]));grouping.value=config.groupResources?'combined':'separate';submit(form,'Save',()=>{o.name=input.value.trim();o.purpose=goal.value;config.groupResources=grouping.value==='combined';message('Objective settings updated');});}
      function todoDialog(item) {const form=dialog('Add a to-do'),input=field(form,'To-do',element('input'));input.type='text';input.required=true;submit(form,'Add',()=>item.checks.push({title:input.value.trim(),done:false}));}
      function detailDialog(item) {const o=objective(),form=dialog('Link task details'),pick=field(form,'Details document',select([{id:'',name:'None'},...o.items.filter(i=>i.kind==='document'||i.kind==='assistant'||i.kind==='notebook').map(i=>({id:i.id,name:i.title}))]));pick.value=item.detail||'';submit(form,'Link',()=>{item.detail=pick.value||null;});}
      function linkTerminalDialog(item) {const form=dialog('Link an existing simulated terminal'),pick=field(form,'Terminal',select(terminals.filter(t=>t.objective===selected).map(t=>({id:t.id,name:t.name}))));if(!pick.options.length){form.insertBefore(element('p','ob-muted','Create a terminal with + Terminal first.'),form.lastChild);return;}submit(form,'Link',()=>{terminals.find(t=>t.id===pick.value).linked=item.id;message('Item linked · terminal launch folder kept');});}
      function deleteDialog(item) {const form=dialog('Delete '+item.title+' from the demo?');submit(form,'Delete',()=>{const o=objective();o.items.splice(o.items.indexOf(item),1);terminals.filter(t=>t.objective===o.id&&t.linked===item.id).forEach(t=>t.linked=null);o.items.filter(i=>i.detail===item.id).forEach(i=>i.detail=null);o.selectedItem=o.items.find(i=>i.listed!==false)?.id||null;message('Deleted simulated item · linked sessions remain');});}
      function simulateCell(source) {
        const rates=source.match(/rates\s*=\s*\[([\d.,\s]+)\]/);if(rates&&source.includes('mean_rate')){const values=rates[1].split(',').map(Number);return 'Mean verification rate: '+(values.reduce((a,b)=>a+b,0)/values.length*100).toFixed(1)+'%';}
        const text=source.match(/print\(\s*['"]([^'"]*)['"]\s*\)/);if(text)return text[1];
        const number=source.match(/print\(\s*(\d+(?:\.\d+)?)\s*([+*/-])\s*(\d+(?:\.\d+)?)\s*\)/);if(number){const a=Number(number[1]),b=Number(number[3]);return String(({'+':()=>a+b,'-':()=>a-b,'*':()=>a*b,'/':()=>a/b})[number[2]]());}
        return 'Simulated cell finished.';
      }
      function runCommand(t) {
        const command=(t.draft||'').trim();if(!command)return;const o=objectives.find(o=>o.id===t.objective),tree=o.worktrees.find(tree=>tree.id===t.tree),files=o.items.filter(i=>i.listed===false&&i.scope===t.tree);let output;
        if(command==='clear'){t.logs=[];t.draft='';render();return;}
        if(command==='pwd')output='/demo/'+(tree?tree.repo+'/worktrees/'+tree.name:'objectives/'+o.id);
        else if(command==='ls')output=files.map(i=>i.title).join('\n')||'documents/\nnotebooks/\ntasks/';
        else if(command.startsWith('cat ')){const item=files.find(i=>i.title===command.slice(4).trim());output=item?(item.body||''):'No such simulated file.';}
        else if(command.startsWith('echo '))output=command.slice(5);
        else if(command==='help')output='pwd · ls · cat <path> · echo <text> · clear\ndone marks the linked task complete.\nAny other text produces a simulated agent response.';
        else if(command==='done'){const item=o.items.find(i=>i.id===t.linked&&i.kind==='task');if(item){item.checks.forEach(c=>c.done=true);output='Linked task complete.';}else output='Link this terminal to a task first.';}
        else output='Simulated agent completed: '+command;
        t.logs=[...(t.logs||[]),'$ '+command,output].slice(-40);t.draft='';t.state='ready';render();message(t.name+' · simulated result ready to review');
      }
      function render() {renderFocus();renderOverview();renderReader();renderTerminals();persist();}
      render();
      find('reset').onclick=()=>{const form=dialog('Reset all simulated changes?');submit(form,'Reset demo',()=>{restore(JSON.parse(JSON.stringify(fresh)));message('Demo reset to its sample data');});};
      if(window.parent!==window)window.parent.postMessage({channel,type:'ready'},'*');else hydrated=true;
    })();
