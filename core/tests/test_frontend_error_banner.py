"""Error floods must leave navigation and dismissal usable in Chrome."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_error_flood_keeps_controls_usable_and_dismissal_preserves_diagnostics(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not Path(chrome).is_file() or not shutil.which('node'):
        pytest.skip('Chrome and Node required')
    template = (ROOT / 'core/src/core/templates/index.html').read_text()
    banner = template[template.index('<!-- JS error banner'):template.index('<div class="topbar">')]
    page = tmp_path / 'banner.html'
    page.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                    '<button id="underlying" style="position:fixed;inset:0;width:100vw;height:100vh" '
                    'onclick="window.clicks=(window.clicks||0)+1">Lab controls</button>'
                    + banner + '</body></html>')
    interactions = r'''
async function evaluate(expression) {
  const value=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(value.exceptionDetails)throw Error(value.exceptionDetails.exception?.description||value.exceptionDetails.text);
  return value.result.value;
}
async function click(selector) {
  const point=await evaluate(`(()=>{const el=document.querySelector('${selector}'),r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
}
const flood=()=>evaluate(`for(let i=0;i<1000;i++)window.dispatchEvent(new ErrorEvent('error',{message:"Cannot read properties of null (reading 'dataset')",filename:'/static/js/lab-app.js',lineno:3698}));`);
await flood();
await evaluate(`(()=>{
  const box=document.getElementById('__js_errors__'),r=box.getBoundingClientRect();
  if(r.height>100||r.width>360||r.top<innerHeight-120)throw Error('Error flood covers the page');
  if(!box.querySelector('pre').hidden)throw Error('Error details must start collapsed');
  if(!box.getAttribute('data-errors').includes('×1000'))throw Error('Repeated errors were not grouped');
})()`);
await writeFile(domPath.replace('.html','-toast.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
await click('.js-error-preview');
if(await evaluate('window.clicks')!==1)throw Error('Error preview blocks underlying controls');
await click('[data-error-details]');
await evaluate(`(()=>{
  const box=document.getElementById('__js_errors__'),details=box.querySelector('pre');
  if(details.hidden||box.querySelector('[data-error-details]').getAttribute('aria-expanded')!=='true')throw Error('Details cannot be opened');
  for(let i=0;i<100;i++)window.dispatchEvent(new ErrorEvent('error',{message:'Different error '+i+' '+ 'x'.repeat(5000)}));
  if(details.getBoundingClientRect().height>144||box.getAttribute('data-errors').length>41000)throw Error('Error details grow without a bound');
})()`);
await send('Emulation.setDeviceMetricsOverride',{width:320,height:480,deviceScaleFactor:1,mobile:false});
await evaluate(`(()=>{
  const box=document.getElementById('__js_errors__'),r=box.getBoundingClientRect(),close=box.querySelector('[data-error-dismiss]'),c=close.getBoundingClientRect();
  if(r.left<0||r.right>innerWidth||r.height>240)throw Error('Banner does not fit a small viewport');
  if(document.elementFromPoint(c.x+c.width/2,c.y+c.height/2)!==close)throw Error('Dismiss button is obscured');
})()`);
await writeFile(domPath.replace('.html','-details.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
await click('[data-error-dismiss]');
await flood();
await evaluate(`(()=>{
  const box=document.getElementById('__js_errors__');
  if(box.style.display!=='none')throw Error('Repeated errors reopened the dismissed banner');
  if(!box.getAttribute('data-errors').includes('dataset'))throw Error('Dismissal erased diagnostics');
})()`);
// A new page starts notifications again; Escape dismisses without blocking input.
await send('Page.navigate',{url:pageUrl});
await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
await flood();
await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
if(await evaluate("document.getElementById('__js_errors__').style.display")!=='none')throw Error('Escape did not dismiss errors');
'''
    driver = (ROOT / 'scripts/chrome-dump-auth.mjs').read_text()
    script = tmp_path / 'check-banner.mjs'
    script.write_text(driver.replace('const evaluated = await send(', interactions + '\nconst evaluated = await send(', 1))
    profile = tmp_path / 'profile'
    browser = subprocess.Popen([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
                                '--no-default-browser-check', '--user-data-dir=' + str(profile),
                                '--remote-debugging-port=0', 'about:blank'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (profile / 'DevToolsActivePort').exists():
            assert browser.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', str(script), str(profile), page.as_uri(), str(tmp_path / 'rendered.html')],
                                env={**os.environ, 'LAB_UI_AUTH_COOKIE': ''}, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        print('Banner screenshots: ' + str(tmp_path))
    finally:
        if browser.poll() is None:
            os.killpg(browser.pid, signal.SIGTERM)
        browser.wait(timeout=5)
