// Actual Lab sidebar, authenticated Git APIs, native CDP mouse filter clicks.
// Picker search uses native text; select controls dispatch their change event.
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const [base, workspace, output] = process.argv.slice(2);
const fixtures = JSON.parse(process.env.LAB_COMPARISON_FIXTURES);
const projects = JSON.parse(process.env.LAB_COMPARISON_PROJECTS);
const internalDocument = JSON.parse(process.env.LAB_COMPARISON_DOCUMENT);
const profile = await mkdtemp(join(tmpdir(), 'lab-comparison-chrome-'));
const chrome = spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], {stdio: 'ignore'});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const result = {rows: [], errors: [], scopeInput: 'CDP mouse and text search', filterInput: 'CDP mouse', picker: {},scopeControls:[]};
let ws;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try {port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break;} catch {}
    if (chrome.exitCode !== null) throw Error('Chrome exited before startup');
    await sleep(100);
  }
  if (!port) throw Error('Chrome did not start');
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method: 'PUT'}).then(r => r.json());
  ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const entry = pending.get(message.id);
      pending.delete(message.id);
      message.error ? entry.reject(message.error) : entry.resolve(message.result);
    }
    if (message.method === 'Runtime.exceptionThrown') result.errors.push(message.params.exceptionDetails);
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') result.errors.push(message.params.args);
  };
  await new Promise(resolve => {ws.onopen = resolve;});
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const key = ++id;
    pending.set(key, {resolve, reject});
    ws.send(JSON.stringify({id: key, method, params}));
  });
  const evaluate = async expression => {
    const response = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  };
  const wait = async expression => {
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      if (await evaluate(expression)) return;
      await sleep(25);
    }
    const shot=await send('Page.captureScreenshot',{format:'png'});
    await writeFile(join(output,'failure.png'),Buffer.from(shot.data,'base64'));
    throw Error('Timeout: ' + expression + ' sidebar=' + await evaluate('document.getElementById("sidebar")?.textContent')+' context='+await evaluate('JSON.stringify({session:typeof termCurrentSession==="undefined"?null:termCurrentSession,workspace:typeof termCurrentWorkspaceId==="undefined"?null:termCurrentWorkspaceId,toast:document.querySelector(".explorer-toast")?.textContent,logical:typeof termSessions==="undefined"?null:termSessions.map(row=>({name:row.name,logical_name:row.logical_name,root:row.linked_scope?.root})),scope:typeof _termSelectedScope==="undefined"?null:_termSelectedScope()})'));
  };
  const click = async (selector,clickCount=1) => {
    await evaluate('new Promise(resolve=>requestAnimationFrame(resolve))');
    const box = await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing control');el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount, ...box});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount, ...box});
  };
  const doubleClick=async selector=>{await click(selector);await click(selector,2);};
  const type = async (selector, text) => { await click(selector);await send('Input.insertText',{text}); };
  const choose = async (selector, value) => evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const selectScope = async path => {
    await click('.sidebar-scope-add');
    await wait('!document.querySelector(".sidebar-scope-picker [data-status]")?.textContent.includes("Loading")');
    await send('Input.insertText',{text:path});
    await click(`.sidebar-scope-picker [data-scope-option="${path}"]`);
    await wait(`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(path)}`);
  };
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Network.enable');
  await send('Network.setCookie', {name: 'lab_session', value: process.env.LAB_PROBE_COOKIE, url: base, httpOnly: true});
  await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
  const config = {recentMode: 'local-main', showRecent: true, recentSort: 'name',
    folderScopes: projects, worktreeColorsVersion: 2};
  const storageKey = 'labSidebarFileConfig-v2:' + encodeURIComponent(workspace);
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `localStorage.setItem('labTermAutoSpawn','0');localStorage.setItem('labSidebarPct:workspace:comparisons','26');if(!localStorage.getItem(${JSON.stringify(storageKey)}))localStorage.setItem(${JSON.stringify(storageKey)},${JSON.stringify(JSON.stringify(config))});`});
  await send('Page.navigate', {url: base + '/?workspace=' + encodeURIComponent(workspace)});
  await wait('!!document.querySelector(".sidebar-scope-add")');
  for (const fixture of fixtures) {
    await click('.sidebar-scope-add');
    await wait(`!!document.querySelector('.sidebar-scope-picker [data-scope-option="${fixture.path}"]') && !document.querySelector('.sidebar-scope-picker [data-status]')?.textContent.includes('Loading')`);
    await send('Input.insertText', {text: fixture.path});
    await wait(`document.querySelectorAll('.sidebar-scope-picker [data-scope-option]').length===1`);
    await click(`.sidebar-scope-picker [data-scope-option="${fixture.path}"]`);
    await wait(`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(fixture.path)}`);
    const control=await evaluate(`(()=>{const chip=document.querySelector('.sidebar-scope-chip.active');return {label:chip.querySelector('.sidebar-file-scope-button').textContent,kind:chip.dataset.scopeKind,badge:chip.querySelector('.sidebar-scope-tag').textContent,historyEnabled:!chip.querySelector('.sidebar-repo-history').disabled,terminalEnabled:!chip.querySelector('.sidebar-link-terminal').disabled,allInline:Array.from(chip.querySelectorAll('button')).every(button=>{const r=button.getBoundingClientRect(),p=chip.getBoundingClientRect();return r.top>=p.top && r.bottom<=p.bottom}),inactiveDisabled:Array.from(document.querySelectorAll('.sidebar-scope-chip:not(.active) .sidebar-repo-history,.sidebar-scope-chip:not(.active) .sidebar-link-terminal')).every(button=>button.disabled),repeatedBranch:!!document.querySelector('.sidebar-worktree-current,.sidebar-worktree-picker')};})()`);
    const isWorktree=fixture.path!==fixture.project;
    const expectedLabel=fixture.project.split('/').pop()+'/'+fixture.branch;
    if((fixture.branch==='HEAD'?!control.label.includes('(detached)'):control.label!==expectedLabel)||control.kind!==(isWorktree?'worktree':'folder')||control.badge!==(isWorktree?'Worktree':'Folder')||!control.historyEnabled||!control.terminalEnabled||!control.allInline||!control.inactiveDisabled||control.repeatedBranch)throw Error('Incorrect inline scope controls: '+JSON.stringify({fixture,control}));
    result.scopeControls.push({scope:fixture.label,...control});
    for (const mode of ['uncommitted', 'local-main']) {
      const selector = `.sidebar-recent-selector[data-recent-mode="${mode}"]`;
      if (await evaluate(`document.querySelector('.sidebar-recent-selector.active')?.dataset.recentMode===${JSON.stringify(mode)}`)) {
        await click(selector);
        await wait('!document.querySelector(".sidebar-recent-selector.active")');
      }
      await click(selector);
      const rows = `Array.from(document.querySelectorAll('[data-project-recent] .sidebar-file[data-filepath]'),el=>el.dataset.filepath).sort()`;
      await wait(`document.querySelector('.sidebar-recent-selector.active')?.dataset.recentMode===${JSON.stringify(mode)} && JSON.stringify(${rows})===${JSON.stringify(JSON.stringify(fixture.expected[mode]))}`);
      await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
      const bounds = await evaluate(`(()=>{const r=document.getElementById('sidebar').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:Math.min(r.height,650),scale:1};})()`);
      const screenshot = await send('Page.captureScreenshot', {format: 'png', clip: bounds});
      const name = fixture.label + '-' + mode + '.png';
      await writeFile(join(output, name), Buffer.from(screenshot.data, 'base64'));
      result.rows.push({scope: fixture.label, branch: fixture.branch, mode,
        files: await evaluate(rows), screenshot: name});
      console.log(fixture.label + ' / ' + mode + ': ' + fixture.expected[mode].join(', '));
    }
  }
  // The new row exposes the current scope only until the user pins it.
  result.picker.visibleBeforePin = await evaluate('Array.from(document.querySelectorAll(".sidebar-file-scope-button"),node=>node.dataset.folderPath)');
  if (result.picker.visibleBeforePin.length !== 1) throw Error('Unpinned inactive projects remained visible');
  const last = fixtures.at(-1), first = fixtures[0];
  result.picker.automaticColors = await evaluate('_sidebarFileConfig.folderScopes.filter(row=>row.color!=="#6e7681").map(row=>row.color)');
  if (new Set(result.picker.automaticColors).size !== result.picker.automaticColors.length) throw Error('Automatic colors were reused before the palette was exhausted');
  await click(`.sidebar-scope-pin[data-scope-path="${last.path}"]`);
  await click(`.sidebar-file-scope-button[data-folder-path="${last.path}"]`);
  await click('.sidebar-scope-add');
  await wait('!document.querySelector(".sidebar-scope-picker [data-status]")?.textContent.includes("Loading")');
  result.picker.mostUsed = await evaluate('document.querySelector(".sidebar-scope-picker [data-scope-option]")?.dataset.scopeOption');
  if (result.picker.mostUsed !== last.path) throw Error('Usage sorting did not put the most recent tie first');
  const pickerShot = await send('Page.captureScreenshot', {format: 'png'});
  await writeFile(join(output, 'scope-picker.png'), Buffer.from(pickerShot.data, 'base64'));
  result.picker.kindFilters=[];
  const replaceText=async (selector,text)=>{
    await click(selector);
    await send('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:4,commands:['SelectAll']});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:4});
    if(text)await send('Input.insertText',{text});
    else {
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace'});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace'});
    }
  };
  for(const query of ['worktree','branch','main','master']) {
    await replaceText('.sidebar-scope-picker [data-search]',query);
    const worktrees=query==='worktree'||query==='branch';
    await wait(`document.querySelector('.sidebar-scope-picker [data-search]').value===${JSON.stringify(query)} && Array.from(document.querySelectorAll('.sidebar-scope-picker [data-scope-option]')).every(node=>(node.dataset.scopeKind==='worktree')===${worktrees})`);
    const rows=await evaluate(`Array.from(document.querySelectorAll('.sidebar-scope-picker [data-scope-option]'),node=>({path:node.dataset.scopeOption,kind:node.dataset.scopeKind,icon:!!node.querySelector('.sidebar-scope-kind svg'),color:getComputedStyle(node.querySelector('.sidebar-scope-kind')).color,badge:node.querySelector('.sidebar-scope-type')?.textContent}))`);
    if(!rows.length || rows.some(row=>!row.icon || worktrees && row.badge!=='Worktree'))throw Error('Missing scope icons or type filters');
    result.picker.kindFilters.push({query,rows});
    if(query==='worktree') {
      const shot=await send('Page.captureScreenshot',{format:'png'});
      await writeFile(join(output,'worktree-picker-filter.png'),Buffer.from(shot.data,'base64'));
    }
  }
  await replaceText('.sidebar-scope-picker [data-search]','');
  await send('Input.insertText', {text: first.path});
  await click(`.sidebar-scope-picker [data-scope-option="${first.path}"]`);
  await wait(`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(first.path)}`);
  result.picker.visibleAfterSwitch = await evaluate('Array.from(document.querySelectorAll(".sidebar-file-scope-button"),node=>node.dataset.folderPath)');
  if (result.picker.visibleAfterSwitch.length !== 2 || !result.picker.visibleAfterSwitch.includes(last.path)) throw Error('Pinned scope did not survive switching');
  result.picker.scopeRows=await evaluate(`Array.from(document.querySelectorAll('.sidebar-scope-chip,.sidebar-scope-add'),node=>{const r=node.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,width:r.width}})`);
  if(result.picker.scopeRows.some((row,index,rows)=>index && row.top<rows[index-1].bottom))throw Error('Scopes or + button share a line');
  await click(`.sidebar-scope-color[data-scope-path="${first.path}"]`);
  const paletteButtons = await evaluate('Array.from(document.querySelectorAll(".sidebar-scope-palette [data-color]"),node=>node.dataset.color)');
  if (paletteButtons.length !== 20 || new Set(paletteButtons).size !== 20) throw Error('Expected 20 distinct fixed colors');
  await click('.sidebar-scope-palette [data-color="#d4d73b"]');
  result.picker.colors = await evaluate('_sidebarFileConfig.folderScopes.filter(row=>row.color!=="#6e7681").map(row=>({path:row.path,color:row.color}))');
  if (!result.picker.colors.some(row=>row.path===first.path && row.color==='#d4d73b')) throw Error('Manual color did not save');
  const afterShot = await send('Page.captureScreenshot', {format: 'png'});
  await writeFile(join(output, 'pinned-scopes.png'), Buffer.from(afterShot.data, 'base64'));
  const masterFolder=fixtures.find(row=>row.branch==='master'&&row.path===row.project);
  await selectScope(masterFolder.path);
  const primaryShot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(join(output,'inline-folder-worktree-controls.png'),Buffer.from(primaryShot.data,'base64'));
  if(!await evaluate('Array.from(document.querySelectorAll(".sidebar-scope-chip:not(.active) .sidebar-repo-history")).every(button=>button.disabled)'))throw Error('Inactive GitHub control remained enabled');
  await selectScope(first.path);
  const oldOrigin = await evaluate('performance.timeOrigin');
  await send('Page.reload');
  await wait(`performance.timeOrigin!==${oldOrigin} && typeof _sidebarFileConfig!=='undefined' && document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(first.path)}`);
  result.picker.reload = await evaluate(`({pins:_sidebarFileConfig.pinnedScopes,color:_sidebarFileConfig.folderScopes.find(row=>row.path===${JSON.stringify(first.path)})?.color})`);
  if (!result.picker.reload.pins.includes(last.path) || result.picker.reload.color !== '#d4d73b') throw Error('Pins or colors were lost on reload');
  // Settings define allowed metadata types without navigating the workspace.
  await click('.sidebar-file-config-cog');
  await wait('!!document.querySelector("#labSettingsCenter [name=filesSort]")');
  if(await evaluate('!!document.querySelector("#labSettingsCenter [data-folders],#labSettingsCenter [data-add-folder],#labSettingsCenter [data-worktree-colors],#labSettingsCenter [data-project-settings]")'))throw Error('Duplicate project settings are still visible');
  const scopePreferenceKeys=['folderScopes','selectedFolders','selectedWorktrees','pinnedScopes','scopeUsage','terminalScopePins','rootScopeColors','rootWorktreeFolders','worktreeColors'];
  const readScopePreferences=()=>evaluate(`Object.fromEntries(${JSON.stringify(scopePreferenceKeys)}.map(key=>[key,_sidebarFileConfig[key]]))`);
  const beforeFileSave=await readScopePreferences();
  await choose('#labSettingsCenter [name=filesSort]','type');
  await click('#labSettingsCenter [type=submit]');
  await wait('document.querySelector("#labSettingsCenter [data-message]")?.textContent==="Saved"');
  const afterFileSave=await readScopePreferences();
  if(JSON.stringify(beforeFileSave)!==JSON.stringify(afterFileSave))throw Error('File preference save changed projects, pins, usage, or colors');
  result.settings={duplicateProjectControls:false,preservedScopePreferences:scopePreferenceKeys};
  const settingsShot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(join(output,'file-sidebar-settings.png'),Buffer.from(settingsShot.data,'base64'));
  await click('#labSettingsCenter [data-scope=global]');
  await click('#labSettingsCenter [data-section=links]');
  await wait('document.querySelectorAll("#labSettingsCenter [data-link-type]").length===3');
  await click('#labSettingsCenter [data-add-type]');
  await type('#labSettingsCenter [data-link-type]:last-child [data-name]', 'Design');
  await click('#labSettingsCenter [type=submit]');
  await wait('document.querySelector("#labSettingsCenter [data-message]")?.textContent==="Saved"');
  await click('#labSettingsCenter [data-done]');
  result.links = {selectInput:'DOM type select change event',documentInput:'native CDP clicks and text search',textInput:'native CDP text',customType:'Design',metadataEntry:'scope double-click'};
  await wait('!!document.querySelector("[data-edit-links]")');
  await doubleClick('.sidebar-file-scope-button.active');
  await wait('!document.querySelector(".scope-links-dialog [data-add-link]").disabled');
  for (const [index,kind,label,url,tab] of [
    [1,'google-docs','Google proposal','https://docs.google.com/document/d/fixture/edit'],
    [2,'jira','LAB-1','https://tickets.example.invalid/browse/LAB-1'],
    [3,'internal-docs','Whole proposal',null,null],
    [4,'internal-docs','Implementation tab',null,internalDocument.tab_id],
  ]) {
    await click('.scope-links-dialog [data-add-link]');
    const card=`.scope-links-dialog [data-link-card]:nth-child(${index})`;
    await choose(card+' [data-type]',kind);
    await type(card+' [data-label]',label);
    if(url) await type(card+' [data-url]',url);
    else {
      await wait(`document.querySelectorAll(${JSON.stringify(card+' [data-document]')}).length>=3`);
      await type(card+' [data-document-search]','no-matching-document');
      if(await evaluate(`document.querySelectorAll(${JSON.stringify(card+' [data-document]')}).length`))throw Error('Unmatched document search retained rows');
      await replaceText(card+' [data-document-search]','implementation');
      await wait(`document.querySelectorAll(${JSON.stringify(card+' [data-document]')}).length===1`);
      await click(card+` [data-document="${internalDocument.document_id}"]`);
      await wait(`!document.querySelector(${JSON.stringify(card)})._targetLoading && !!document.querySelector(${JSON.stringify(card+' [data-tab="'+internalDocument.tab_id+'"]')})`);
      await click(card+` [data-tab="${tab||''}"]`);
      if(tab) {
        const pickerShot=await send('Page.captureScreenshot',{format:'png'});
        await writeFile(join(output,'internal-document-picker.png'),Buffer.from(pickerShot.data,'base64'));
      }
      await click(card+' [data-finish-document]');
      if(!await evaluate(`document.querySelector(${JSON.stringify(card+' [data-document-picker]')}).hidden`))throw Error('Document browser did not collapse to selected destination');
    }
  }
  const editorShot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(join(output,'scope-links-editor.png'),Buffer.from(editorShot.data,'base64'));
  await click('.scope-links-dialog [type=submit]');
  await wait('!document.querySelector(".scope-links-dialog") && document.querySelectorAll(".sidebar-scope-link").length===4');
  const linkData=await evaluate(`fetch('/api/scope-links?path='+encodeURIComponent(${JSON.stringify(first.path)})).then(r=>r.json())`);
  if(linkData.links[2].tab_id!==null || linkData.links[3].tab_id!==internalDocument.tab_id)throw Error('Document/tab identities did not save');
  result.links.saved=linkData.links.map(link=>({type:link.type,label:link.label,document_id:link.document_id,tab_id:link.tab_id}));
  await click('[data-scope-link="0"]');
  await click('[data-scope-link="1"]');
  await click('[data-scope-link="3"]');
  await wait('document.querySelector("#assistantModalDocument")?.textContent.includes("Implementation tab content.")');
  result.links.tabOpened=await evaluate('document.querySelector("#assistantDocumentLocation")?.textContent');
  await click('[data-scope-link="2"]');
  await wait('document.querySelector("#assistantModalDocument")?.textContent.includes("Proposal main document content.")');
  result.links.wholeDocumentOpened=await evaluate('document.querySelector("#assistantDocumentLocation")?.textContent');
  await click('[data-scope-link="3"]');
  await wait('document.querySelector("#assistantModalDocument")?.textContent.includes("Implementation tab content.")');
  const linksShot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(join(output,'worktree-links.png'),Buffer.from(linksShot.data,'base64'));
  await doubleClick(`.sidebar-file-scope-button[data-folder-path="${last.path}"]`);
  await wait(`!!document.querySelector('.scope-links-dialog') && !document.querySelector('.scope-links-dialog [data-add-link]').disabled && document.querySelector('[data-scope-links]')?.dataset.scopeLinks===${JSON.stringify(last.path)}`);
  if(await evaluate('document.querySelectorAll(".sidebar-scope-link").length || document.querySelectorAll(".scope-links-dialog [data-link-card]").length'))throw Error('Double-click edited the wrong checkout');
  await click('.scope-links-dialog [data-close]');
  await selectScope(first.path);
  await wait('document.querySelectorAll(".sidebar-scope-link").length===4');
  await doubleClick('.sidebar-file-scope-button.active');
  await wait('document.querySelectorAll(".scope-links-dialog [data-link-card]").length===4 && !Array.from(document.querySelectorAll(".scope-links-dialog [data-link-card]")).some(node=>node._targetLoading)');
  const internalCard='.scope-links-dialog [data-link-card]:nth-child(4)';
  if(!await evaluate(`document.querySelector(${JSON.stringify(internalCard+' [data-document-picker]')}).hidden`))throw Error('Saved document target was not compact');
  await click(internalCard+' [data-change-document]');
  await click(internalCard+' [data-tab=""]');
  await click(internalCard+' [data-finish-document]');
  await click('.scope-links-dialog [type=submit]');
  await wait('!document.querySelector(".scope-links-dialog")');
  const changed=await evaluate(`fetch('/api/scope-links?path='+encodeURIComponent(${JSON.stringify(first.path)})).then(r=>r.json())`);
  if(changed.links[3].tab_id!==null || changed.links[3].id!==linkData.links[3].id)throw Error('Editing a tab link did not preserve its identity or select the whole document');
  await doubleClick('.sidebar-file-scope-button.active');
  await wait('document.querySelectorAll(".scope-links-dialog [data-link-card]").length===4 && !Array.from(document.querySelectorAll(".scope-links-dialog [data-link-card]")).some(node=>node._targetLoading)');
  await click(internalCard+' [data-change-document]');
  await click(internalCard+` [data-tab="${internalDocument.tab_id}"]`);
  await click(internalCard+' [data-finish-document]');
  await click('.scope-links-dialog [type=submit]');
  await wait('!document.querySelector(".scope-links-dialog")');
  result.links.documentPicker={contentSearch:true,emptySearch:true,doubleClickInactiveScope:true,doubleClickBranchLabel:true,existingLinkEdit:true,mobileFits:false};
  // Create only a disposable plain terminal through the actual New menu.
  await click('#termNewBtn');
  await wait('document.getElementById("termNewPicker").classList.contains("open")');
  await click('#termNewPicker [data-term-option=terminal]');
  await wait('termSessions.length===1 && !!termCurrentSession');
  const session=await evaluate('termSessions[0]');
  result.terminal={name:session.name,createdScope:session.linked_scope?.root};
  if(session.linked_scope?.root!==first.path)throw Error('New terminal lost the direct worktree identity');
  await wait(`_sidebarFileConfig.pinnedScopes.includes(${JSON.stringify(first.path)})`);
  await selectScope(last.path);
  if(await evaluate(`_sidebarFileConfig.pinnedScopes.includes(${JSON.stringify(last.path)})`))await click(`.sidebar-scope-pin[data-scope-path="${last.path}"]`);
  await click('.sidebar-scope-chip.active .sidebar-link-terminal');
  await wait(`termSessions[0]?.linked_scope?.root===${JSON.stringify(last.path)} && _sidebarFileConfig.pinnedScopes.includes(${JSON.stringify(last.path)})`);
  result.terminal.attachedScope=await evaluate('termSessions[0].linked_scope');
  result.terminal.pinned=true;
  await evaluate(`fetch('/api/term/sessions/'+encodeURIComponent(${JSON.stringify(session.name)})+'?purge=true',{method:'DELETE'}).then(r=>{if(!r.ok)throw Error('Owned terminal cleanup failed')})`);
  // Exercise the mobile editor after desktop terminal checks; resizing the
  // viewport also changes the app's independent terminal/sidebar layout.
  await selectScope(first.path);
  await doubleClick('.sidebar-file-scope-button.active');
  await wait('document.querySelectorAll(".scope-links-dialog [data-link-card]").length===4 && !Array.from(document.querySelectorAll(".scope-links-dialog [data-link-card]")).some(node=>node._targetLoading)');
  await click(internalCard+' [data-change-document]');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector(${JSON.stringify(internalCard+' [data-document-picker]')}).scrollIntoView({block:'center'})`);
  const fits=await evaluate(`(()=>{const dialog=document.querySelector('.scope-links-dialog'),r=dialog.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+1 && dialog.scrollWidth<=dialog.clientWidth+1 && Array.from(dialog.querySelectorAll('.scope-document-columns')).every(node=>node.scrollWidth<=node.clientWidth+1)})()`);
  if(!fits)throw Error('Document picker overflows on mobile');
  const mobileShot=await send('Page.captureScreenshot',{format:'png'});
  await writeFile(join(output,'internal-document-picker-mobile.png'),Buffer.from(mobileShot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  result.links.documentPicker.mobileFits=fits;
  await click('.scope-links-dialog [data-close]');
  if (result.errors.length) throw Error('Browser errors: ' + JSON.stringify(result.errors));
  await rm(join(output,'failure.png'),{force:true});
} finally {
  await writeFile(join(output, 'browser.json'), JSON.stringify(result, null, 2) + '\n');
  ws?.close();
  const stopped = chrome.exitCode === null ? new Promise(resolve => chrome.once('exit', resolve)) : Promise.resolve();
  chrome.kill('SIGTERM');
  await Promise.race([stopped, sleep(5000)]);
  if (chrome.exitCode === null) {chrome.kill('SIGKILL'); await stopped;}
  await rm(profile, {recursive: true, force: true});
}
