import {readFile, writeFile} from 'node:fs/promises';

const [userDataDir, pageUrl, domPath, screenshotPath = ''] = process.argv.slice(2);
const cookie = process.env.LAB_UI_AUTH_COOKIE || '';
if (!userDataDir || !pageUrl || !domPath) {
  throw new Error('usage: chrome-dump-auth.mjs <user-data-dir> <url> <dom-path> [screenshot-path]');
}

const [port] = (await readFile(`${userDataDir}/DevToolsActivePort`, 'utf8')).trim().split(/\s+/);
const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method: 'PUT'}).then(response => {
  if (!response.ok) throw new Error(`could not create Chrome target (${response.status})`);
  return response.json();
});

const ws = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let nextId = 1;
ws.addEventListener('message', event => {
  const message = JSON.parse(String(event.data));
  if (!message.id) return;
  const waiter = pending.get(message.id);
  if (!waiter) return;
  pending.delete(message.id);
  if (message.error) waiter.reject(new Error(message.error.message || 'CDP error'));
  else waiter.resolve(message.result || {});
});
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, {once: true});
  ws.addEventListener('error', reject, {once: true});
});

function send(method, params = {}) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params}));
  });
}

await send('Network.enable');
if (cookie) {
  await send('Network.setCookie', {
    name: 'lab_session',
    value: cookie,
    url: new URL(pageUrl).origin,
    httpOnly: true,
    sameSite: 'Strict',
  });
}
await send('Emulation.setDeviceMetricsOverride', {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});
await send('Page.enable');
const loaded = new Promise(resolve => {
  const listener = event => {
    const message = JSON.parse(String(event.data));
    if (message.method !== 'Page.loadEventFired') return;
    ws.removeEventListener('message', listener);
    resolve();
  };
  ws.addEventListener('message', listener);
});
await send('Page.navigate', {url: pageUrl});
await Promise.race([loaded, new Promise(resolve => setTimeout(resolve, 8000))]);
await new Promise(resolve => setTimeout(resolve, 4500));

const evaluated = await send('Runtime.evaluate', {
  expression: 'document.documentElement.outerHTML',
  returnByValue: true,
});
await writeFile(domPath, String(evaluated.result?.value || ''), 'utf8');
if (screenshotPath) {
  const screenshot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  await writeFile(screenshotPath, Buffer.from(screenshot.data || '', 'base64'));
}
ws.close();
