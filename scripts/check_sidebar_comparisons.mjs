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
const result = {rows: [], errors: [], scopeInput: 'CDP mouse and text search', filterInput: 'CDP mouse', picker: {}};
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
    throw Error('Timeout: ' + expression + ' sidebar=' + await evaluate('document.getElementById("sidebar")?.textContent'));
  };
  const click = async selector => {
    const box = await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el)throw Error('Missing control');el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...box});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...box});
  };
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
  await send('Input.insertText', {text: first.path});
  await click(`.sidebar-scope-picker [data-scope-option="${first.path}"]`);
  await wait(`document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(first.path)}`);
  result.picker.visibleAfterSwitch = await evaluate('Array.from(document.querySelectorAll(".sidebar-file-scope-button"),node=>node.dataset.folderPath)');
  if (result.picker.visibleAfterSwitch.length !== 2 || !result.picker.visibleAfterSwitch.includes(last.path)) throw Error('Pinned scope did not survive switching');
  await click(`.sidebar-scope-color[data-scope-path="${first.path}"]`);
  const paletteButtons = await evaluate('Array.from(document.querySelectorAll(".sidebar-scope-palette [data-color]"),node=>node.dataset.color)');
  if (paletteButtons.length !== 20 || new Set(paletteButtons).size !== 20) throw Error('Expected 20 distinct fixed colors');
  await click('.sidebar-scope-palette [data-color="#d4d73b"]');
  result.picker.colors = await evaluate('_sidebarFileConfig.folderScopes.filter(row=>row.color!=="#6e7681").map(row=>({path:row.path,color:row.color}))');
  if (!result.picker.colors.some(row=>row.path===first.path && row.color==='#d4d73b')) throw Error('Manual color did not save');
  const afterShot = await send('Page.captureScreenshot', {format: 'png'});
  await writeFile(join(output, 'pinned-scopes.png'), Buffer.from(afterShot.data, 'base64'));
  const oldOrigin = await evaluate('performance.timeOrigin');
  await send('Page.reload');
  await wait(`performance.timeOrigin!==${oldOrigin} && typeof _sidebarFileConfig!=='undefined' && document.querySelector('[data-project-sidebar]')?.dataset.projectSidebar===${JSON.stringify(first.path)}`);
  result.picker.reload = await evaluate(`({pins:_sidebarFileConfig.pinnedScopes,color:_sidebarFileConfig.folderScopes.find(row=>row.path===${JSON.stringify(first.path)})?.color})`);
  if (!result.picker.reload.pins.includes(last.path) || result.picker.reload.color !== '#d4d73b') throw Error('Pins or colors were lost on reload');
  // Settings define allowed metadata types without navigating the workspace.
  await click('.sidebar-file-config-cog');
  await wait('!!document.querySelector("#labSettingsCenter [data-section=files]")');
  await click('#labSettingsCenter [data-scope=global]');
  await click('#labSettingsCenter [data-section=links]');
  await wait('document.querySelectorAll("#labSettingsCenter [data-link-type]").length===3');
  await click('#labSettingsCenter [data-add-type]');
  await type('#labSettingsCenter [data-link-type]:last-child [data-name]', 'Design');
  await click('#labSettingsCenter [type=submit]');
  await wait('document.querySelector("#labSettingsCenter [data-message]")?.textContent==="Saved"');
  await click('#labSettingsCenter [data-done]');
  result.links = {selectInput:'DOM select change event',textInput:'native CDP text',customType:'Design'};
  await wait('!!document.querySelector("[data-edit-links]")');
  await click('[data-edit-links]');
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
      await wait(`!!document.querySelector(${JSON.stringify(card+' [data-document]')})`);
      await type(card+' [data-document-search]','Feature proposal');
      await choose(card+' [data-document]',internalDocument.document_id);
      await wait(`document.querySelector(${JSON.stringify(card+' [data-tab]')})?.disabled===false`);
      if(tab) await choose(card+' [data-tab]',tab);
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
  await selectScope(last.path);
  await wait(`document.querySelector('[data-scope-links]')?.dataset.scopeLinks===${JSON.stringify(last.path)} && !!document.querySelector('[data-edit-links]')`);
  if(await evaluate('document.querySelectorAll(".sidebar-scope-link").length'))throw Error('Links leaked into another checkout');
  await selectScope(first.path);
  await wait('document.querySelectorAll(".sidebar-scope-link").length===4');
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
  await click('.sidebar-link-terminal');
  await wait(`termSessions[0]?.linked_scope?.root===${JSON.stringify(last.path)} && _sidebarFileConfig.pinnedScopes.includes(${JSON.stringify(last.path)})`);
  result.terminal.attachedScope=await evaluate('termSessions[0].linked_scope');
  result.terminal.pinned=true;
  await evaluate(`fetch('/api/term/sessions/'+encodeURIComponent(${JSON.stringify(session.name)})+'?purge=true',{method:'DELETE'}).then(r=>{if(!r.ok)throw Error('Owned terminal cleanup failed')})`);
  if (result.errors.length) throw Error('Browser errors: ' + JSON.stringify(result.errors));
} finally {
  await writeFile(join(output, 'browser.json'), JSON.stringify(result, null, 2) + '\n');
  ws?.close();
  const stopped = chrome.exitCode === null ? new Promise(resolve => chrome.once('exit', resolve)) : Promise.resolve();
  chrome.kill('SIGTERM');
  await Promise.race([stopped, sleep(5000)]);
  if (chrome.exitCode === null) {chrome.kill('SIGKILL'); await stopped;}
  await rm(profile, {recursive: true, force: true});
}
