/* Independent Chrome windows aligned with Lab's central work area. */
(() => {
  'use strict';
  const preference = 'labAutoDockAssets-v1';
  let current = null, alert = null, sessionEnabled = null;
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const find = (s, name) => s.panel.querySelector(`[data-dock-${name}]`);
  const say = (s, text) => { find(s, 'status').textContent = text; };
  function autoEnabled() {
    if (sessionEnabled !== null) return sessionEnabled;
    try { return localStorage.getItem(preference) !== 'false'; } catch { return true; }
  }
  async function command(owner, operation, extra = {}) {
    const response = await fetch('/api/ui/window-dock', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({owner, operation, ...extra}), signal:AbortSignal.timeout(70000),
    });
    const result = await response.json();
    if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Window docking is unavailable.');
    return result;
  }
  function notice(detail, url = '', blocked = false) {
    alert?.remove();
    alert = document.createElement('aside'); alert.className = 'lab-dock-alert'; alert.setAttribute('role', 'alert');
    const message = document.createElement('p');
    message.textContent = (blocked ? '' : 'Opened as a regular pop-out. ') + detail + ' See Settings → Window docking for setup.';
    const settings = document.createElement('button'); settings.type = 'button'; settings.textContent = 'Window docking settings';
    settings.dataset.dockSettings = ''; settings.onclick = () => window.LabSettings?.open({section:'docking'});
    const close = document.createElement('button'); close.type = 'button'; close.textContent = '×'; close.setAttribute('aria-label', 'Dismiss docking alert');
    close.dataset.dockAlertDismiss = ''; close.onclick = () => { alert?.remove(); alert = null; };
    alert.append(message, settings);
    if (blocked && url) {
      const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Open site';
      alert.append(link);
    }
    alert.append(close);
    // An asset editor may already be modal. Keep its fallback message reachable.
    const dialog = [...document.querySelectorAll('dialog[open]')].at(-1), node = alert;
    (dialog || document.body).append(node);
    dialog?.addEventListener('close', () => { if (alert === node) document.body.append(node); }, {once:true});
  }
  function restoreTitle(s) {
    if (s.marking && document.title === 'Lab dock parent ' + s.owner) document.title = s.originalTitle;
    s.marking = false;
  }
  // Called on success AND every failure/cancel path. Never close a requested site.
  function navigate(s) {
    if (!s.popup) return;
    const popup = s.popup; s.popup = null;
    try {
      if (popup.closed) return;
      const link = popup.document.createElement('a'); link.href = s.url; link.rel = 'noreferrer';
      popup.document.body.append(link); link.click();
    } catch { notice('The popup could not navigate. Allow pop-ups for Lab, then use Open site.', s.url, true); }
  }
  function buttons(s) {
    for (const name of ['start', 'url', 'permission', 'check']) {
      const node = find(s, name); if (node) node.disabled = s.pending || s.active || (name === 'start' && !s.trusted);
    }
    find(s, 'detach').disabled = !s.active && !s.pending;
    find(s, 'close').disabled = !s.active || s.pending;
  }
  function layout(s) {
    // The main column's margins already exclude Lab's sidebar and terminal.
    const host = document.getElementById('content');
    if (!host?.getClientRects().length) return;
    const r = host.getBoundingClientRect();
    const shellTop = parseFloat(getComputedStyle(document.querySelector('.layout') || host).paddingTop) || 0;
    const sidebar = document.getElementById('sidebar');
    const left = Math.max(0, r.left, sidebar?.getClientRects().length ? sidebar.getBoundingClientRect().right : 0);
    const top = Math.max(0, shellTop, r.top);
    Object.assign(s.panel.style, {left:left+'px', top:top+'px', right:'auto', bottom:'auto',
      width:Math.max(0, Math.min(innerWidth,r.right)-left)+'px', height:Math.max(0,innerHeight-top-8)+'px'});
  }
  function rectangle(s) {
    layout(s);
    const r = find(s, 'slot').getBoundingClientRect();
    if (r.width < 320 || r.height < 180) throw Error('Enlarge Lab’s central area or reduce the terminal width to dock this window.');
    return [r.left/innerWidth, r.top/innerHeight, r.width/innerWidth, r.height/innerHeight];
  }
  function cleanup(s) {
    clearTimeout(s.timer); clearTimeout(s.deadline); clearInterval(s.layoutTimer); s.observer?.disconnect();
    s.active = false; s.pending = false; restoreTitle(s);
  }
  function retire(s, detail = '') {
    if (s.retired) return;
    s.retired = true; cleanup(s); navigate(s); s.panel.remove();
    if (current === s) current = null;
    // A late attach response also gets its own detach below. Owners never change.
    void command(s.owner, 'detach').catch(() => {});
    if (detail) notice(detail);
  }
  async function check(s, operation = 'status') {
    if (s.pending || s.active) return;
    s.pending = true; buttons(s); say(s, operation === 'permission' ? 'Opening macOS Accessibility settings…' : 'Checking the local window helper…');
    try {
      const result = await command(s.owner, operation);
      if (s.retired) return;
      s.trusted = result.ok && result.trusted === true; say(s, result.detail);
    } catch (error) { if (!s.retired) say(s, error.message); }
    finally { s.pending = false; buttons(s); }
  }
  async function heartbeat(s) {
    if (s.retired || !s.active) return;
    if (!s.host?.isConnected || !s.host.getClientRects().length) { retire(s); return; }
    try {
      const result = await command(s.owner, 'update', {slot:rectangle(s), visible:!document.hidden && !document.querySelector('dialog[open]')});
      if (s.retired) return;
      if (!result.ok || !result.active) throw Error(result.detail || 'The window helper disconnected.');
      s.panel.dataset.geometry = JSON.stringify({parent:result.parent, popup:result.popup, target:result.target});
    } catch (error) { if (!s.retired) retire(s, error.message); return; }
    if (!s.retired) s.timer = setTimeout(() => heartbeat(s), 1000);
  }
  async function start(s, value, features) {
    if (s.pending || s.active || s.retired) return;
    let url; try { url = new URL(value); } catch {}
    if (!url || !['http:', 'https:'].includes(url.protocol)) { say(s, 'Enter a complete HTTP or HTTPS URL.'); return; }
    s.url = url.href;
    // Open synchronously in the asset click. Keep only a temporary blank handle.
    try { s.popup = window.open('about:blank', '_blank', features || 'popup,width=900,height=650'); }
    catch (error) { retire(s); notice(error.message || 'Allow pop-ups for Lab.', s.url, true); return; }
    if (!s.popup) { retire(s); notice('Allow pop-ups for this Lab address in Chrome, then open the asset again.', s.url, true); return; }
    s.pending = true; buttons(s);
    try {
      s.popup.opener = null;
      const policy = s.popup.document.createElement('meta'); policy.name = 'referrer'; policy.content = 'no-referrer'; s.popup.document.head.append(policy);
      s.popup.document.title = 'Lab dock popup ' + s.owner;
      s.popup.document.body.textContent = 'Opening your site and aligning it with Lab…';
      rectangle(s);
      // First builds may be slow. Fall back promptly, without ever attaching after cancellation.
      s.deadline = setTimeout(() => retire(s, 'The window helper took too long. Check permission and helper setup, then try again.'), 8000);
      say(s, 'Checking window control…');
      const ready = await command(s.owner, 'status');
      if (s.retired) return;
      if (!ready.ok || !ready.trusted) throw Error(ready.detail || 'Enable Lab Window Dock in macOS Privacy & Security → Accessibility.');
      s.originalTitle = document.title; s.marking = true; document.title = 'Lab dock parent ' + s.owner;
      say(s, 'Aligning the window with Lab…');
      await new Promise(resolve => setTimeout(resolve, 250));
      if (s.retired) return;
      const result = await command(s.owner, 'attach', {slot:rectangle(s), visible:!document.hidden && !document.querySelector('dialog[open]')});
      if (s.retired) { void command(s.owner, 'detach').catch(() => {}); return; }
      if (!result.ok || !result.active) throw Error(result.detail || 'Could not dock this popup.');
      clearTimeout(s.deadline); s.pending = false; s.active = true;
      restoreTitle(s); navigate(s); buttons(s);
      say(s, 'Docked. Detach keeps the site open as a regular window.');
      void heartbeat(s);
    } catch (error) { if (!s.retired) retire(s, error.message); }
  }
  async function end(s, operation = 'detach') {
    if (s.pending || operation === 'detach' && s.automatic) { retire(s); return; }
    s.pending = true; clearTimeout(s.timer); buttons(s);
    try {
      const result = await command(s.owner, operation);
      if (s.retired) return;
      if (!result.ok || result.active) throw Error(result.detail || 'Could not release the docked window.');
      if (s.automatic) { retire(s); return; }
      s.active = false; say(s, result.detail);
    } catch (error) { if (!s.retired) retire(s, error.message); }
    finally { s.pending = false; buttons(s); }
  }
  function panel(host, automatic = false) {
    if (current) retire(current);
    const s = {owner:id(), host, automatic, panel:document.createElement('section')}; current = s;
    s.panel.className = 'lab-window-dock'; s.panel.setAttribute('aria-label', automatic ? 'Docked asset window' : 'Docked window prototype');
    s.panel.innerHTML = `<div class="lab-window-dock-heading"><strong>${automatic ? 'Asset window' : 'Docked window · Mac prototype'}</strong><button type="button" data-dock-dismiss>${automatic ? 'Back to Lab' : 'Exit trial'}</button></div>
      <div class="lab-window-dock-controls">${automatic ? '' : `<input type="url" data-dock-url aria-label="Docked website URL" value="https://example.com/">
      <button type="button" data-dock-permission>Enable window control</button><button type="button" data-dock-check>Check permission</button><button type="button" data-dock-start disabled>Dock</button>`}
      <button type="button" data-dock-detach disabled>Detach</button><button type="button" data-dock-close disabled>Close popup</button></div>
      <p data-dock-status role="status"></p><div data-dock-slot><p>The website’s window will sit here.</p></div>`;
    document.body.append(s.panel); layout(s);
    s.layoutTimer = setInterval(() => layout(s), 200);
    find(s, 'detach').onclick = () => end(s); find(s, 'close').onclick = () => end(s, 'close');
    find(s, 'dismiss').onclick = () => retire(s);
    if (automatic && host) {
      s.observer = new MutationObserver(() => retire(s)); s.observer.observe(host, {childList:true});
    }
    return s;
  }
  function open(host) {
    if (current && !current.automatic) return;
    if (!window.LAB_NATIVE_BROWSER_REUSE) return;
    const s = panel(host);
    find(s, 'start').onclick = () => start(s, find(s, 'url').value);
    find(s, 'permission').onclick = () => check(s, 'permission'); find(s, 'check').onclick = () => check(s);
    void check(s);
  }
  function openAsset(url, features) {
    if (!autoEnabled()) return false;
    if (current) retire(current);
    alert?.remove(); alert = null;
    if (!window.LAB_NATIVE_BROWSER_REUSE) {
      window.open(url, '_blank', features);
      notice('Automatic docking requires Google Chrome on the Mac running Lab.'); return true;
    }
    const host = document.getElementById('content');
    if (!host?.getClientRects().length) {
      window.open(url, '_blank', features); notice('Open Lab’s central work area before docking.'); return true;
    }
    const s = panel(host, true);
    // noopener would hide the handle even when the popup succeeds. Clear it ourselves before navigation.
    void start(s, url, features.split(',').filter(item => !['noopener','noreferrer'].includes(item)).join(','));
    return true;
  }
  function renderSettings(host) {
    host.innerHTML = `<p class="settings-intro">Asset links can open in a real Chrome window aligned with Lab’s central area. If docking fails, the site opens as a regular pop-out with a dismissible setup message.</p>
      <label class="settings-check"><span class="settings-field-copy"><span>Automatically dock asset links</span><small>Applies immediately in this browser. Command/Ctrl-click still opens a tab.</small></span><input type="checkbox" role="switch" data-dock-auto></label>
      <p class="settings-hint">Requires Google Chrome on the Mac running Lab, Xcode Command Line Tools, and macOS System Settings → Privacy &amp; Security → Accessibility → Lab Window Dock. Allow pop-ups for Lab in Chrome.</p>
      <div class="settings-actions"><button type="button" data-dock-permission>Enable window control</button><button type="button" data-dock-check>Check permission</button></div><p role="status" data-dock-settings-status></p>`;
    const toggle = host.querySelector('[data-dock-auto]'), status = host.querySelector('[data-dock-settings-status]');
    toggle.checked = autoEnabled(); toggle.onchange = () => {
      const enabled = toggle.checked;
      try { localStorage.setItem(preference, String(enabled)); sessionEnabled = null; status.textContent = 'Saved for this browser.'; }
      catch { sessionEnabled = enabled; status.textContent = 'Applied for this session; browser storage is unavailable.'; }
      if (!enabled && current?.automatic) retire(current);
    };
    const controls = [...host.querySelectorAll('button')], owner = id();
    const checkSetup = async operation => {
      controls.forEach(button => button.disabled = true); status.textContent = 'Checking the local window helper…';
      try { const result = await command(owner, operation); if (host.isConnected) status.textContent = result.detail; }
      catch (error) { if (host.isConnected) status.textContent = error.message; }
      finally { controls.forEach(button => button.disabled = false); }
    };
    if (!window.LAB_NATIVE_BROWSER_REUSE) {
      controls.forEach(button => button.disabled = true); status.textContent = 'Native docking is available only to a local administrator on macOS. Open Lab locally in Chrome.';
    } else {
      controls[0].onclick = () => checkSetup('permission'); controls[1].onclick = () => checkSetup('status'); void checkSetup('status');
    }
  }
  window.addEventListener('pagehide', () => {
    if (!current) return;
    const s = current; s.retired = true; cleanup(s); navigate(s); s.panel.remove(); current = null;
    navigator.sendBeacon('/api/ui/window-dock', new Blob([JSON.stringify({owner:s.owner, operation:'detach'})], {type:'application/json'}));
  });
  window.LabWindowDock = {open, openAsset, renderSettings, detach:() => { if (current?.automatic) retire(current); }};
})();
