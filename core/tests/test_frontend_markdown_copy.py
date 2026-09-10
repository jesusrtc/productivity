"""Exercise actual Markdown parsing, disclosure state and clipboard payloads in Chrome."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_markdown_disclosures_and_clipboard(tmp_path):
    chrome = (os.environ.get('CHROME_BIN') or shutil.which('chromium')
              or shutil.which('google-chrome')
              or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if not Path(chrome).is_file():
        pytest.skip('Chrome is required for the real DOM/clipboard regression check')
    app = (STATIC / 'js/lab-app.js').read_text()
    wrappers = app[app.index('  async function copyForGDocs(e) {'):
                   app.index('  // Attach (or replace) the online URL')]
    assistant = (STATIC / 'js/views/assistant.js').read_text()
    actions = assistant[assistant.index('  function addCopyButtons('):
                        assistant.index('  async function refresh(')]
    scripts = '\n'.join('<script>' + (STATIC / path).read_text() + '</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js',
        'vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js',
    ])
    markdown = '''# Report

![Chart](data:image/png;base64,aW1hZ2U=#chart.png)

## Repeat

First section.

<details>
<summary>Query</summary>

HIDDEN_PROMPT

![Hidden image](data:image/png;base64,aW1hZ2U=#hidden.png)

<details open>
<summary>Open child of closed parent</summary>

HIDDEN_CHILD

</details>

</details>

<details open>
<summary>Python and data</summary>

```python
print("VISIBLE_CODE")
```

| Name | Value |
| --- | --- |
| Sample | 42 |

## INTERNAL_HEADING

More visible text.

<details>
<summary>Nested secret</summary>

NESTED_SECRET

</details>

</details>

After disclosure.

## Repeat

SECOND_SECTION

## Generate content

Generated text.

<details>
<summary>Private notes</summary>

GENERATED_SECRET

</details>
'''
    checks = r'''
(async () => {
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const source = document.getElementById('workspaceDocBody');
  source.innerHTML = LabMarkdown.render(MARKDOWN);
  const closed = source.querySelector('details');
  const open = source.querySelector('details[open]');
  assert(closed && !closed.open && open.open, 'default disclosure state');
  assert(source.querySelector('pre code.language-python'), 'Markdown code inside details');
  assert(source.querySelector('details table tbody td').textContent === 'Sample', 'Markdown table inside details');
  const sanitized = LabMarkdown.render('<details open ontoggle="alert(1)"><summary>Safe</summary><img src=x onerror="alert(2)"><script>alert(3)<\/script><iframe srcdoc="bad"></iframe><p style="position:fixed">Text</p><a href="javascript:alert(1)">link</a></details>');
  const safe = document.createElement('div'); safe.innerHTML = sanitized;
  assert(safe.querySelector('details[open] summary'), 'safe HTML preserved');
  assert(!safe.querySelector('script,iframe,[onerror],[ontoggle],[style],a[href]'), 'active HTML removed');
  const copied = [];
  const fetched = [];
  window.fetch = async url => { fetched.push(url); return {ok:true, blob: async () => new Blob(['image'], {type:'image/png'})}; };
  const clipboard = {write: async items => {
    const item = items[0];
    copied.push({html: await (await item.getType('text/html')).text(), plain: await (await item.getType('text/plain')).text()});
  }, writeText: async plain => copied.push({plain})};
  Object.defineProperty(navigator, 'clipboard', {value: clipboard, configurable:true});
  const button = document.getElementById('copy');
  const event = {target:button};
  const sourceBefore = source.innerHTML;
  assert(await copyForGDocs(event), 'whole document copy succeeds');
  let output = copied.at(-1);
  for (const key of ['html','plain']) {
    assert(output[key].includes('VISIBLE_CODE') && output[key].includes('42'), 'visible rich content included in ' + key);
    assert(!/HIDDEN_PROMPT|HIDDEN_CHILD|NESTED_SECRET|GENERATED_SECRET|Nested secret|Query/.test(output[key]), 'closed content omitted in ' + key);
  }
  assert(!output.html.includes('<details') && !output.html.includes('<summary'), 'open disclosures flattened');
  assert(!fetched.some(url => url.includes('hidden.png')), 'closed images are not fetched');
  assert(source.innerHTML === sourceBefore, 'copy leaves source unchanged');
  assert(!document.body.classList.contains('light-mode'), 'copy leaves page theme unchanged');

  // Toggle the live DOM, then take a snapshot before asynchronous image work.
  closed.querySelector('summary').click();
  assert(closed.open, 'native click expands disclosure');
  const pending = copyForGDocs(event);
  closed.open = false;
  await pending;
  assert(copied.at(-1).plain.includes('HIDDEN_PROMPT') && copied.at(-1).plain.includes('HIDDEN_CHILD'), 'snapshot uses state at click');

  // Duplicate section titles and an internal heading must not confuse boundaries.
  const topHeadings = Array.from(source.children).filter(el => el.tagName === 'H2');
  const sectionButton = document.createElement('button'); sectionButton.textContent = 'Copy';
  topHeadings[0].appendChild(sectionButton);
  await copySectionByHeading(sectionButton);
  output = copied.at(-1);
  assert(output.plain.includes('After disclosure.') && output.plain.includes('INTERNAL_HEADING'), 'fold heading does not truncate outer section');
  assert(!output.plain.includes('SECOND_SECTION'), 'section stops at next sibling heading');
  topHeadings[1].appendChild(sectionButton);
  await copySectionByHeading(sectionButton);
  assert(copied.at(-1).plain.includes('SECOND_SECTION') && !copied.at(-1).plain.includes('First section.'), 'duplicate title selects clicked section');
  sectionButton.remove();

  // Assistant uses the same live-DOM copy for whole sections and generated content.
  addCopyButtons(source);
  const realCopy = LabMarkdown.copy;
  let actionPromise;
  LabMarkdown.copy = (...args) => (actionPromise = realCopy(...args));
  topHeadings[0].querySelector('button:last-child').click();
  await actionPromise;
  assert(copied.at(-1).plain.includes('After disclosure.') && !copied.at(-1).plain.includes('HIDDEN_PROMPT'), 'Assistant section uses live state');
  topHeadings[2].querySelector('button').click();
  await actionPromise;
  LabMarkdown.copy = realCopy;
  assert(copied.at(-1).plain === 'Generated text.', 'generated content excludes heading and closed notes: ' + copied.at(-1).plain);

  // Rich-clipboard rejection must not leak raw Markdown via the fallback.
  clipboard.write = async () => { throw new Error('denied'); };
  const originalExec = document.execCommand;
  document.execCommand = command => {
    assert(command === 'copy', 'copy fallback command');
    const data = {};
    const fallbackEvent = new Event('copy', {cancelable:true});
    Object.defineProperty(fallbackEvent, 'clipboardData', {value:{setData:(type,value) => { data[type] = value; }}});
    document.dispatchEvent(fallbackEvent);
    copied.push({html:data['text/html'], plain:data['text/plain']});
    return true;
  };
  assert(await copyForGDocs(event), 'legacy fallback succeeds');
  assert(!copied.at(-1).plain.includes('HIDDEN_PROMPT') && !copied.at(-1).html.includes('HIDDEN_PROMPT'), 'fallback filters both MIME types');
  await LabMarkdown.copy(source, {plainOnly:true});
  assert(!copied.at(-1).plain.includes('HIDDEN_PROMPT'), 'explicit plain copy filters closed content');
  clipboard.writeText = async () => { throw new Error('denied'); };
  document.execCommand = () => false;
  assert(!(await LabMarkdown.copy(source, {button, plainOnly:true})), 'failure reported');
  assert(button.textContent === 'Copy failed' && !button.disabled, 'failure feedback restores button');
  document.execCommand = originalExec;
  assert(!document.querySelector('textarea'), 'fallback cleanup');
  document.getElementById('result').textContent = 'PASS: disclosure rendering, safety, live state, nested folds, section boundaries, Assistant, both clipboard formats and fallback';
})().catch(error => { document.getElementById('result').textContent = 'FAIL: ' + error.stack; });
'''
    page = tmp_path / 'markdown-copy.html'
    page.write_text('<!doctype html><meta charset="utf-8"><body><button id="copy">Copy</button>'
                    '<div id="workspaceDocBody"></div><pre id="result">PENDING</pre>' + scripts
                    + '<script>const MARKDOWN = ' + json.dumps(markdown) + ';\n'
                    + wrappers + actions + checks + '</script>')
    process = subprocess.Popen([
        chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
        '--no-default-browser-check', '--allow-file-access-from-files',
        '--user-data-dir=' + str(tmp_path / 'chrome-profile'),
        '--dump-dom', '--virtual-time-budget=5000', page.as_uri(),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired as error:
        # Chrome on macOS can emit its completed DOM and then hang during shutdown.
        stdout = (error.stdout or b'').decode()
        stderr = (error.stderr or b'').decode()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    (tmp_path / 'rendered.html').write_text(stdout)
    import re
    result = re.search(r'<pre id="result">(.*?)</pre>', stdout, re.S)
    assert result and result[1].startswith('PASS:'), (result[1] if result else stdout[-1000:]) + stderr[-1000:]
