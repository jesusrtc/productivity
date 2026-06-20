#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';

const baseUrl = (process.argv[2] || process.env.LAB_BASE_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const apiBaseUrl = (() => {
  const url = new URL(baseUrl);
  if (url.hostname === 'localhost') url.hostname = '127.0.0.1';
  return url.toString().replace(/\/$/, '');
})();
const iterations = Number(process.argv[3] || process.env.LAB_PERF_ITERATIONS || 12);
const terminalSamples = Number(process.env.LAB_TERMINAL_SAMPLES || 100);
const loadBudgetMs = Number(process.env.LAB_LOAD_BUDGET_MS || 50);
const shellBudgetMs = Number(process.env.LAB_SHELL_BUDGET_MS || 50);
const terminalP95BudgetMs = Number(process.env.LAB_TERMINAL_P95_BUDGET_MS || 8);
const terminalMaxBudgetMs = process.env.LAB_TERMINAL_MAX_BUDGET_MS == null
  ? null
  : Number(process.env.LAB_TERMINAL_MAX_BUDGET_MS);
const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const repoRoot = resolve(process.cwd());

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

async function fetchOk(url, options = {}) {
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
      return res;
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
      const { resolve: ok, reject } = pending.get(msg.id);
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
      pending.set(id, { resolve: resolveSend, reject });
      setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 15000);
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

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(sorted.length - 1, Math.round((p / 100) * (sorted.length - 1))));
  return sorted[idx];
}

function fmt(n) {
  if (n == null || Number.isNaN(n)) return 'n/a';
  return n.toFixed(1);
}

function query(path, params) {
  const qs = new URLSearchParams(params);
  return `${path}?${qs.toString()}`;
}

async function projectEntries() {
  let dirs = [];
  try {
    dirs = (await readdir(join(repoRoot, 'projects'), { withFileTypes: true }))
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();
  } catch {
    return [];
  }
  const entries = [];
  for (const name of dirs) {
    const abs = join(repoRoot, 'projects', name);
    const projectJson = join(abs, 'project.json');
    let repos = [];
    if (existsSync(projectJson)) {
      try {
        const data = JSON.parse(await readFile(projectJson, 'utf8'));
        const worktrees = Array.isArray(data.worktrees) ? data.worktrees : [];
        repos = worktrees
          .map((wt) => {
            if (typeof wt === 'string') return wt;
            if (wt && typeof wt === 'object') return wt.dir || wt.path || '';
            return '';
          })
          .filter(Boolean)
          .map((dir) => {
            if (dir.startsWith('/')) return dir;
            const projectRelative = join(abs, dir);
            if (existsSync(projectRelative)) return projectRelative;
            return join(repoRoot, dir);
          });
      } catch {}
    }
    entries.push({ name, abs, repos });
  }
  return entries;
}

async function markdownRoute() {
  const candidates = [
    '.agents/memory/MEMORY.md',
    'docs/EXPECTATIONS.md',
    'README.md',
  ];
  for (const path of candidates) {
    if (existsSync(join(repoRoot, path))) {
      return {
        label: 'markdown-view',
        path: query('/view', { path }),
        selector: 'body h1',
      };
    }
  }
  return null;
}

async function routes() {
  const routesOut = [
    { label: 'home-dashboard', path: '/', bodyClass: 'home-active', selector: '#homePanel' },
    { label: 'home-snoozed', path: '/#snoozed', bodyClass: 'home-active', selector: '#homePanel .snooze-section' },
    { label: 'home-timeline', path: '/#timeline', bodyClass: 'home-active', selector: '#homePanel .bucket' },
    { label: 'home-search', path: '/#search', bodyClass: 'home-active', selector: '#searchResults' },
    { label: 'productivity', path: '/?view=productivity', bodyClass: 'self-active', selector: '#selfView' },
    { label: 'cerebro', path: '/?view=cerebro', bodyClass: 'cerebro-active', selector: '#cerebroView' },
    { label: 'code-search', path: '/?view=code-search', bodyClass: 'code-search-active', selector: '#codeSearchView' },
    { label: 'logs-view', path: '/?view=logs', bodyClass: 'logs-active', selector: '#logsTerminal' },
    { label: 'logs-standalone', path: '/logs', selector: '#logsTerminal' },
  ];
  const md = await markdownRoute();
  if (md) routesOut.push(md);

  for (const project of await projectEntries()) {
    routesOut.push({
      label: `project-${project.name}`,
      path: query('/', { project: project.abs }),
      bodyClass: 'project-active',
      selector: '#content h1',
    });
    routesOut.push({
      label: `project-redirect-${project.name}`,
      path: `/p/${encodeURIComponent(project.name)}`,
      bodyClass: 'project-active',
      selector: '#content h1',
    });
    for (const repo of project.repos) {
      routesOut.push({
        label: `repo-${project.name}-${basename(repo)}`,
        path: query('/', { repo }),
        bodyClass: 'project-active',
        selector: '#content h1',
      });
    }
  }
  return routesOut;
}

async function measureRoute(port, route) {
  const samples = [];
  const { client } = await newPage(port);
  try {
    const setupScript = `
      (() => {
        const expectedClass = ${JSON.stringify(route.bodyClass || '')};
        const expectedSelector = ${JSON.stringify(route.selector || '')};
        window.__labPerf = { shellMs: null, errors: [] };
        function err(msg) {
          try { window.__labPerf.errors.push(String(msg)); } catch {}
        }
        window.addEventListener('error', (e) => err((e.message || 'Error') + ' @ ' + (e.filename || '') + ':' + (e.lineno || '?')));
        window.addEventListener('unhandledrejection', (e) => err('Unhandled: ' + (e.reason && e.reason.message ? e.reason.message : e.reason)));
        function visible(el) {
          return !el || !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        }
        function ready() {
          const el = expectedSelector ? document.querySelector(expectedSelector) : null;
          const bodyOk = !expectedClass || (document.body && document.body.classList.contains(expectedClass));
          const selectorOk = !expectedSelector || !!el;
          return selectorOk && (bodyOk || visible(el));
        }
        function tick() {
          try {
            if (window.__labPerf.shellMs == null && ready()) {
              window.__labPerf.shellMs = performance.now();
              return;
            }
          } catch {}
          setTimeout(tick, 0);
        }
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', tick, { once: true });
        } else {
          tick();
        }
      })();
    `;
    await client.send('Page.addScriptToEvaluateOnNewDocument', { source: setupScript });
    for (let i = 0; i < iterations + 1; i++) {
      const loadEvent = client.once('Page.loadEventFired');
      const targetUrl = route.url || (baseUrl + route.path);
      if (i === 0) {
        await client.send('Page.navigate', { url: targetUrl });
      } else {
        await client.send('Page.reload');
      }
      await loadEvent;
      await sleep(5);
      const evalResult = await client.send('Runtime.evaluate', {
      returnByValue: true,
      expression: `(() => {
          const expectedClass = ${JSON.stringify(route.bodyClass || '')};
          const expectedSelector = ${JSON.stringify(route.selector || '')};
          function visible(el) {
            return !el || !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          }
          function shellReady() {
            const el = expectedSelector ? document.querySelector(expectedSelector) : null;
            const bodyOk = !expectedClass || (document.body && document.body.classList.contains(expectedClass));
            const selectorOk = !expectedSelector || !!el;
            return selectorOk && (bodyOk || visible(el));
          }
          if (!window.__labPerf) window.__labPerf = { shellMs: null, errors: [] };
          if (window.__labPerf.shellMs == null && shellReady()) {
            window.__labPerf.shellMs = performance.now();
          }
          const nav = performance.getEntriesByType('navigation')[0];
          const resources = performance.getEntriesByType('resource').map((r) => ({
            name: r.name,
            initiatorType: r.initiatorType,
            duration: r.duration,
            transferSize: r.transferSize,
            encodedBodySize: r.encodedBodySize,
          })).sort((a, b) => b.duration - a.duration).slice(0, 8);
          return {
            href: location.href,
            title: document.title,
            statusText: document.body ? document.body.innerText.slice(0, 80) : '',
            bodyClass: document.body ? document.body.className : '',
            shellMs: window.__labPerf && window.__labPerf.shellMs,
            domContentLoadedMs: nav ? nav.domContentLoadedEventEnd : null,
            loadMs: nav ? nav.loadEventEnd : null,
            responseEndMs: nav ? nav.responseEnd : null,
            transferSize: nav ? nav.transferSize : null,
            encodedBodySize: nav ? nav.encodedBodySize : null,
            jsErrors: [
              ...((window.__labPerf && window.__labPerf.errors) || []),
              ...(document.getElementById('__js_errors__')?.getAttribute('data-errors') || '').split('\\n').filter(Boolean),
            ],
            resources,
          };
        })()`,
      });
      if (i > 0) samples.push(evalResult.result.value);
    }
  } finally {
    try {
      await client.send('Page.close');
    } catch {}
    client.ws.close();
  }
  return samples;
}

function wsUrlFor(resource) {
  const url = new URL(resource, apiBaseUrl);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

function waitForWsOpen(ws) {
  return new Promise((resolveOpen, reject) => {
    ws.addEventListener('open', resolveOpen, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
}

function waitForEcho(ws, marker) {
  let seen = '';
  return new Promise((resolveEcho, reject) => {
    const t0 = performance.now();
    const timeout = setTimeout(() => {
      cleanup();
      reject(new Error(`timed out waiting for terminal echo ${JSON.stringify(marker)}`));
    }, 3000);
    function cleanup() {
      clearTimeout(timeout);
      ws.removeEventListener('message', onMessage);
      ws.removeEventListener('error', onError);
    }
    function onError(err) {
      cleanup();
      reject(err);
    }
    function onMessage(event) {
      const msg = JSON.parse(event.data);
      if (msg.type === 'exit') {
        cleanup();
        reject(new Error(`terminal exited: ${msg.reason || 'unknown'}`));
        return;
      }
      if (msg.type !== 'data') return;
      seen += msg.data || '';
      if (seen.includes(marker)) {
        cleanup();
        resolveEcho(performance.now() - t0);
      }
    }
    ws.addEventListener('message', onMessage);
    ws.addEventListener('error', onError);
  });
}

async function measureTerminalLatency() {
  let sessionName = null;
  let ws = null;
  try {
    const created = await fetchJson(`${apiBaseUrl}/api/term/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        kind: 'terminal',
        cwd: repoRoot,
        name: `perf-latency-${Date.now()}`,
      }),
    });
    sessionName = created.name;
    ws = new WebSocket(wsUrlFor(`/ws/term/${encodeURIComponent(sessionName)}?cols=120&rows=32`));
    await waitForWsOpen(ws);
    await sleep(100);

    const samples = [];
    for (let i = 0; i < terminalSamples; i++) {
      const marker = String.fromCharCode(97 + (i % 26));
      const echo = waitForEcho(ws, marker);
      ws.send(JSON.stringify({ type: 'input', data: marker }));
      samples.push(await echo);
    }
    ws.send(JSON.stringify({ type: 'input', data: '\u0015' }));
    return {
      samples,
      p50: percentile(samples, 50),
      p95: percentile(samples, 95),
      max: Math.max(...samples),
    };
  } finally {
    if (ws) {
      try {
        ws.send(JSON.stringify({ type: 'detach' }));
      } catch {}
      try {
        ws.close();
      } catch {}
    }
    if (sessionName) {
      await fetchOk(`${apiBaseUrl}/api/term/sessions/${encodeURIComponent(sessionName)}?purge=true`, {
        method: 'DELETE',
      }).catch(() => {});
    }
  }
}

async function runMatrix(port) {
  const routeList = await routes();
  const warm = await newPage(port);
  const warmLoad = warm.client.once('Page.loadEventFired');
  await warm.client.send('Page.navigate', { url: baseUrl + '/' });
  await warmLoad;
  await warm.client.send('Page.close').catch(() => {});
  warm.client.ws.close();

  const results = [];
  for (const route of routeList) {
    const samples = await measureRoute(port, route);
    const load = samples.map((s) => s.loadMs).filter((n) => typeof n === 'number');
    const dcl = samples.map((s) => s.domContentLoadedMs).filter((n) => typeof n === 'number');
    const responseEnd = samples.map((s) => s.responseEndMs).filter((n) => typeof n === 'number');
    const shell = samples.map((s) => s.shellMs).filter((n) => typeof n === 'number');
    const badErrors = samples.flatMap((s) => s.jsErrors || []).filter(Boolean);
    const worst = samples.reduce((a, b) => ((b.loadMs || 0) > (a.loadMs || 0) ? b : a), samples[0]);
    const row = {
      label: route.label,
      samples,
      p50Load: percentile(load, 50),
      p95Load: percentile(load, 95),
      maxLoad: Math.max(...load),
      p95Dcl: percentile(dcl, 95),
      p95ResponseEnd: percentile(responseEnd, 95),
      p95Shell: shell.length ? percentile(shell, 95) : null,
      maxShell: shell.length ? Math.max(...shell) : null,
      errors: badErrors,
      worstResources: worst.resources,
    };
    results.push(row);
    console.log([
      route.label.padEnd(34),
      `p95Resp=${fmt(row.p95ResponseEnd)}ms`,
      `p95DCL=${fmt(row.p95Dcl)}ms`,
      `p95Load=${fmt(row.p95Load)}ms`,
      `maxLoad=${fmt(row.maxLoad)}ms`,
      `p95Shell=${fmt(row.p95Shell)}ms`,
      `maxShell=${fmt(row.maxShell)}ms`,
      badErrors.length ? 'JS_ERRORS' : '',
    ].filter(Boolean).join('  '));
  }
  return results;
}

function pageFailures(results) {
  return results.filter((r) =>
    r.p95Load >= loadBudgetMs
    || (r.p95Shell != null && r.p95Shell >= shellBudgetMs)
    || r.errors.length
  );
}

function reportPageFailures(failures) {
  if (!failures.length) return;
  console.log('\nPAGE FAILURES');
  for (const f of failures) {
    console.log(`- ${f.label}: p95Resp=${fmt(f.p95ResponseEnd)} p95DCL=${fmt(f.p95Dcl)} p95Load=${fmt(f.p95Load)} maxLoad=${fmt(f.maxLoad)} p95Shell=${fmt(f.p95Shell)} maxShell=${fmt(f.maxShell)}`);
    if (f.errors.length) console.log(`  jsErrors=${JSON.stringify(f.errors[0]).slice(0, 300)}`);
    for (const res of f.worstResources || []) {
      console.log(`  resource ${res.duration.toFixed(1)}ms ${res.initiatorType} ${res.name.replace(baseUrl, '')}`);
    }
  }
}

async function main() {
  const userDataDir = await mkdtemp(join(tmpdir(), 'lab-perf-chrome-'));
  const port = 9300 + Math.floor(Math.random() * 400);
  const chrome = spawn(chromePath, [
    '--headless=new',
    '--disable-gpu',
    '--disable-background-networking',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-sync',
    '--metrics-recording-only',
    '--no-first-run',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  chrome.stderr.on('data', () => {});

  try {
    await waitForChrome(port);
    const results = await runMatrix(port);
    const failures = pageFailures(results);
    reportPageFailures(failures);

    const terminal = await measureTerminalLatency();
    console.log([
      '\nterminal-echo'.padEnd(35),
      `p50=${fmt(terminal.p50)}ms`,
      `p95=${fmt(terminal.p95)}ms`,
      `max=${fmt(terminal.max)}ms`,
      `n=${terminal.samples.length}`,
    ].join('  '));

    const terminalFailed = terminal.p95 >= terminalP95BudgetMs
      || (terminalMaxBudgetMs != null && terminal.max >= terminalMaxBudgetMs);
    if (terminalFailed) {
      const maxPart = terminalMaxBudgetMs == null ? '' : `, max budget <${terminalMaxBudgetMs}ms`;
      console.log(`\nTERMINAL FAILURE: p95 budget <${terminalP95BudgetMs}ms${maxPart}`);
    }

    if (failures.length || terminalFailed) {
      process.exitCode = 1;
    } else {
      console.log(`\nAll measured pages stayed below p95 ${loadBudgetMs}ms load/${shellBudgetMs}ms shell budgets, and terminal echo stayed within latency budget.`);
    }
  } finally {
    chrome.kill('SIGTERM');
    await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
