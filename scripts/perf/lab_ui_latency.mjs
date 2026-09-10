#!/usr/bin/env node
// Compare unchanged terminal-tab refreshes in an authenticated, isolated browser.
// Usage: node scripts/perf/lab_ui_latency.mjs [local-lab-url] [baseline-git-ref]
// The baseline defaults to HEAD, for comparison against uncommitted UI changes.
// Measures DOM rendering/layout with 30 tabs, not end-to-end keyboard latency.
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const baseUrl = (process.argv[2] || execFileSync('scripts/lab-url.sh', {encoding:'utf8'}).trim()).replace(/\/$/, '');
const baselineRef = process.argv[3] || 'HEAD';
const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function fetchJson(url, options = {}) {
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
      return res.json();
    } catch (err) {
      lastErr = err;
      await sleep(100);
    }
  }
  throw lastErr;
}

async function waitForChrome(port) {
  const url = `http://127.0.0.1:${port}/json/version`;
  const deadline = Date.now() + 10000;
  let lastErr = null;
  while (Date.now() < deadline) {
    try {
      return await fetchJson(url);
    } catch (err) {
      lastErr = err;
      await sleep(100);
    }
  }
  throw lastErr || new Error('timed out waiting for Chrome');
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const listeners = new Map();

  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject, timer } = pending.get(msg.id);
      clearTimeout(timer);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else ok(msg.result || {});
      return;
    }
    if (msg.method && listeners.has(msg.method)) {
      for (const fn of listeners.get(msg.method)) fn(msg.params || {});
    }
  });

  function send(method, params = {}) {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolveSend, reject) => {
      const timer = setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 15000);
      pending.set(id, { resolve: resolveSend, reject, timer });
    });
  }

  function once(method) {
    return new Promise((resolveOnce) => {
      const fn = (params) => {
        const arr = listeners.get(method) || [];
        listeners.set(method, arr.filter((x) => x !== fn));
        resolveOnce(params);
      };
      const arr = listeners.get(method) || [];
      arr.push(fn);
      listeners.set(method, arr);
    });
  }

  return new Promise((resolveConnect, reject) => {
    ws.addEventListener('open', () => resolveConnect({ ws, send, once }));
    ws.addEventListener('error', reject, { once: true });
  });
}

async function newPage(port) {
  const target = await fetchJson(`http://127.0.0.1:${port}/json/new`, { method: 'PUT' });
  const client = await connect(target.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  await client.send('Network.enable');
  return { target, client };
}

async function main() {
  const cookie = execFileSync('core/.venv/bin/python', ['-c', 'from core import auth; print(auth.issue_session(auth.get_user("admin")))'], {encoding:'utf8'}).trim();
  const profile = await mkdtemp(join(tmpdir(), 'lab-ui-latency-'));
  const port = 9700 + Math.floor(Math.random() * 200);
  const chrome = spawn(chromePath, ['--headless=new', '--no-first-run', '--disable-background-networking', '--disable-extensions', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank'], {stdio:'ignore'});
  let client;
  try {
    await waitForChrome(port);
    ({client} = await newPage(port));
    await client.send('Network.setCookie', {name:'lab_session',value:cookie,url:baseUrl,httpOnly:true,sameSite:'Strict'});
    const loaded = client.once('Page.loadEventFired');
    await client.send('Page.navigate', {url:baseUrl+'/?view=productivity&ui_check=1'});
    await loaded;
    await sleep(2000);
    const evaluate = async expression => {
      const r = await client.send('Runtime.evaluate', {expression,returnByValue:true,awaitPromise:true});
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.text+' '+r.exceptionDetails.exception?.description);
      return r.result.value;
    };
    await evaluate(`document.body.classList.add('term-open');
      termSessions = Array.from({length:30},(_,i)=>({name:'ui-perf-'+i,logical_name:'terminal-'+i,kind:'terminal',label:'Terminal '+i,latest_tasks:['A representative request for terminal '+i]}));
      termCurrentSession=termSessions[0].name; termCurrentWorkspaceId=_termActiveWorkspaceId();
      termRenderSessionList();`);
    const before = execFileSync('git',['show',baselineRef+':core/src/core/static/js/lab-app.js'],{encoding:'utf8'});
    const after = await readFile('core/src/core/static/js/lab-app.js','utf8');
    const part = (source,start,end) => source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
    const functions = source => part(source,'  function termRenderSessionList()', '  // One move plan') + part(source,'  function _termRenderActiveSessionHeader()', '  let _termSessionTooltipHideTimer');
    const results = [];
    for (const [version,source] of [['before',before],['after',after],['before',before],['after',after]]) {
      await evaluate(functions(source));
      results.push(await evaluate(`(async () => {
        const target=document.getElementById('termSessionList');
        delete target._labTabsHtml;
        const header=document.getElementById('termActiveSession'); delete header._labHeaderHtml;
        termRenderSessionList(); target.offsetHeight;
        const first=target.firstElementChild;
        const samples=[]; let mutations=0;
        const observer=new MutationObserver(rows=>mutations+=rows.length);
        observer.observe(target,{childList:true,subtree:true});
        for(let i=0;i<50;i++) {
          const start=performance.now(); termRenderSessionList(); target.offsetHeight; samples.push(performance.now()-start);
          await new Promise(resolve=>setTimeout(resolve,0));
        }
        observer.disconnect(); samples.sort((a,b)=>a-b);
        return {version:${JSON.stringify(version)},p50:samples[25],p95:samples[47],max:samples[49],mutations,sameNode:target.firstElementChild===first};
      })()`));
    }
    console.log(JSON.stringify(results,null,2));
  } finally {
    if(client) {await client.send('Page.close').catch(()=>{});client.ws.close();}
    if(chrome.exitCode===null) {chrome.kill();await new Promise(r=>chrome.once('exit',r));}
    await rm(profile,{recursive:true,force:true}).catch(()=>{});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
