#!/usr/bin/env node
// Exercise Lab's copy listener, real xterm selections, and Chrome's clipboard.
// The terminal is browser-only: never attach to or send input to a user session.
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const baseUrl = execFileSync('scripts/lab-url.sh', {encoding: 'utf8'}).trim();
const chromePath = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const cases = JSON.parse(await readFile('core/tests/fixtures/terminal-copy.json', 'utf8'));
const cookie = execFileSync('core/.venv/bin/python', ['-c',
  'from core import auth; print(auth.issue_session(auth.get_user("admin")))',
], {encoding: 'utf8'}).trim();
const profile = await mkdtemp(join(tmpdir(), 'lab-terminal-copy-'));
const chrome = spawn(chromePath, [
  '--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], {stdio: 'ignore'});
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws, ownsClipboard = false;
let nextId = 0;
const pending = new Map();
function send(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {pending.delete(id); reject(new Error('Timed out: ' + method));}, 15000);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true, userGesture: true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}

try {
  let port;
  const deadline = Date.now() + 15000;
  while (!port) {
    try {port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0];} catch {}
    if (chrome.exitCode != null || Date.now() > deadline) throw new Error('Chrome did not start');
    if (!port) await pause(50);
  }
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method: 'PUT'}).then(r => r.json());
  ws = new WebSocket(target.webSocketDebuggerUrl);
  ws.addEventListener('message', event => {
    const message = JSON.parse(String(event.data)), waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id); clearTimeout(waiter.timer);
    if (message.error) waiter.reject(new Error(message.error.message));
    else waiter.resolve(message.result);
  });
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, {once: true});
    ws.addEventListener('error', reject, {once: true});
  });
  await send('Page.enable');
  await send('Network.enable');
  await send('Network.setCookie', {name: 'lab_session', value: cookie, url: baseUrl, httpOnly: true, sameSite: 'Strict'});
  await send('Browser.grantPermissions', {origin: new URL(baseUrl).origin, permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite']});
  await send('Emulation.setDeviceMetricsOverride', {width: 1200, height: 900, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url: baseUrl + '/?view=productivity&ui_check=1'});
  const readyDeadline = Date.now() + 15000;
  while (!await evaluate('typeof termEnsureXterm === "function"')) {
    if (Date.now() > readyDeadline) throw new Error('Lab did not load');
    await pause(50);
  }
  await evaluate('ensureTerminalLibs()');
  await send('Emulation.setFocusEmulationEnabled', {enabled: true});
  await send('Page.bringToFront');
  // Establish test-owned clipboard content before any read. Never inspect
  // clipboard contents left by the user or another application.
  await evaluate('navigator.clipboard.writeText("Lab clipboard test")');
  ownsClipboard = true;
  await evaluate(`(() => {
    // A fresh profile has no selected terminal. Refuse to replace one if a
    // future startup flow attaches it automatically.
    if (termXterm || termWS) throw new Error('Unexpected existing terminal');
    document.body.classList.add('term-open');
    document.body.classList.remove('term-collapsed');
    const body = document.getElementById('termBody');
    body.style.cssText = 'position:fixed;inset:80px 20px 20px;z-index:99999;background:#0a0e13';
    const host = document.createElement('div'); body.appendChild(host);
    termEnsureXterm(); termXterm.open(host);
    // The test sets each grid size explicitly; page-layout observers must
    // not refit this browser-only terminal between selection and copy.
    termFitAddon = null;
    window.__copyTest = {host, events:0};
    document.addEventListener('copy', event => { if (event.isTrusted) __copyTest.events++; }, true);
  })()`);
  for (const test of cases.flatMap(test => [test.cols, test.cols + 20, Math.max(20, test.cols - 6)].map(cols => ({...test, cols})))) {
    await evaluate(`(async () => {
      termXterm.reset(); termXterm.resize(${test.cols}, 30);
      await new Promise(resolve => termXterm.write(${JSON.stringify(test.text.replace(/\n/g, '\r\n'))}, resolve));
      const buffer = termXterm.buffer.active;
      termXterm.select(0, 0, (buffer.baseY + buffer.cursorY) * termXterm.cols + buffer.cursorX);
      termXterm.focus();
    })()`);
    const copied = await evaluate('document.execCommand("copy")');
    if (!copied) throw new Error(test.name + ': browser refused copy');
    const actual = await evaluate('navigator.clipboard.readText()');
    if (actual !== test.expected) {
      throw new Error(test.name + '\nExpected: ' + JSON.stringify(test.expected) + '\nActual:   ' + JSON.stringify(actual));
    }
    console.log('PASS ' + test.name + ' (' + test.cols + ' columns)');
  }
  // A partial selection must not pick up text outside the selected range.
  await evaluate(`(async () => {
    termXterm.reset(); await new Promise(resolve => termXterm.write('before selected after', resolve));
    termXterm.select(7, 0, 8); termXterm.focus();
    document.execCommand('copy');
  })()`);
  if (await evaluate('navigator.clipboard.readText()') !== 'selected') throw new Error('Partial selection changed');
  console.log('PASS partial selection');
  const count = await evaluate('__copyTest.events');
  if (count !== cases.length * 3 + 1) throw new Error('Expected trusted browser copy events, got ' + count);
  // Select with a real mouse drag for the shortcut check.
  const selection = await evaluate(`(async () => {
    termXterm.clearSelection();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const rect = termXterm.element.querySelector('.xterm-screen').getBoundingClientRect();
    return {left:rect.left, top:rect.top, cellWidth:rect.width / termXterm.cols, cellHeight:rect.height / termXterm.rows};
  })()`);
  const startX = selection.left + selection.cellWidth * 7.1;
  const endX = selection.left + selection.cellWidth * 15.1;
  const y = selection.top + selection.cellHeight / 2;
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', x: startX, y, button: 'left', buttons: 1, clickCount: 1});
  await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: endX, y, buttons: 1});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: endX, y, button: 'left', clickCount: 1});
  if (await evaluate('termXterm.getSelection()') !== 'selected') throw new Error('Mouse selection failed');
  console.log('PASS mouse drag selection');
  // Check the platform copy shortcut as well as the browser Copy command.
  await evaluate('navigator.clipboard.writeText("clipboard shortcut sentinel")');
  const modifiers = process.platform === 'darwin' ? 4 : 2;
  // CDP supplies the OS editing command explicitly for synthetic shortcuts:
  // https://github.com/ChromeDevTools/devtools-protocol/blob/master/pdl/domains/Input.pdl
  await send('Input.dispatchKeyEvent', {type: 'rawKeyDown', key: 'c', code: 'KeyC', windowsVirtualKeyCode: 67, modifiers, commands: ['Copy']});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'c', code: 'KeyC', windowsVirtualKeyCode: 67, modifiers});
  if (await evaluate('navigator.clipboard.readText()') !== 'selected') throw new Error('Native copy shortcut failed');
  console.log('PASS native copy shortcut');
  if (process.env.UI_SCREENSHOT) {
    const shot = await send('Page.captureScreenshot', {format: 'png'});
    await writeFile(process.env.UI_SCREENSHOT, Buffer.from(shot.data, 'base64'));
  }
  console.log('Terminal clipboard browser checks passed.');
} finally {
  if (ws?.readyState === WebSocket.OPEN) {
    if (ownsClipboard) await evaluate('navigator.clipboard.writeText("")').catch(() => {});
    await evaluate('termXterm?.dispose()').catch(() => {});
    await send('Page.close').catch(() => {});
    ws.close();
  }
  if (chrome.exitCode === null) {chrome.kill(); await new Promise(resolve => chrome.once('exit', resolve));}
  await rm(profile, {recursive: true, force: true}).catch(() => {});
}
