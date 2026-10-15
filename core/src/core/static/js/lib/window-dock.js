/* One opt-in native window over a reserved Lab rectangle. No iframe or site scripting. */
(() => {
  let panel = null, owner = null, active = false, busy = false, timer = null;
  let sourceHost = null, originalTitle = null, marking = false;
  const find = name => panel?.querySelector(`[data-dock-${name}]`);
  function say(text) { if (find('status')) find('status').textContent = text; }
  function buttons() {
    if (!panel) return;
    find('start').disabled = busy || active || panel.dataset.trusted !== 'true';
    find('detach').disabled = busy || !active;
    find('close').disabled = busy || !active;
    find('url').disabled = busy || active;
    find('permission').disabled = busy || active;
    find('check').disabled = busy || active;
  }
  function rectangle() {
    const r = find('slot').getBoundingClientRect();
    return [r.left / innerWidth, r.top / innerHeight, r.width / innerWidth, r.height / innerHeight];
  }
  async function command(operation, extra = {}) {
    const response = await fetch('/api/ui/window-dock', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({owner, operation, ...extra}), signal:AbortSignal.timeout(70000),
    });
    const result = await response.json();
    if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Window docking is unavailable.');
    return result;
  }
  function restoreTitle() {
    if (marking && document.title === 'Lab dock parent ' + owner) document.title = originalTitle;
    marking = false;
  }
  function stop() { active = false; clearTimeout(timer); timer = null; restoreTitle(); buttons(); }
  async function check(operation = 'status') {
    if (busy || active) return;
    busy = true; buttons(); say(operation === 'permission' ? 'Opening macOS Accessibility settings…' : 'Checking the local window helper…');
    try {
      const result = await command(operation);
      panel.dataset.trusted = String(result.trusted === true && result.ok);
      say(result.detail);
    } catch (error) { say(error.message); }
    finally { busy = false; buttons(); }
  }
  async function heartbeat() {
    if (!active) return;
    if (!sourceHost?.isConnected || !sourceHost.getClientRects().length) {
      await end('detach'); panel?.remove(); panel = null; return;
    }
    try {
      const result = await command('update', {
        slot:rectangle(), visible:!document.hidden && !document.querySelector('dialog[open]'),
      });
      if (!result.ok || !result.active) { say(result.detail); stop(); return; }
      // Actual helper frames remain inspectable via lab ui / browser diagnostics.
      panel.dataset.geometry = JSON.stringify({parent:result.parent, popup:result.popup, target:result.target});
    } catch (error) { say(error.message + ' The helper will detach if connection is lost.'); }
    if (active) timer = setTimeout(heartbeat, 1000);
  }
  async function start() {
    if (busy || active || panel.dataset.trusted !== 'true') return;
    let url;
    try { url = new URL(find('url').value); } catch {}
    if (!url || !['http:', 'https:'].includes(url.protocol)) { say('Enter a complete HTTP or HTTPS URL.'); return; }
    const r = find('slot').getBoundingClientRect();
    if (r.width < 320 || r.height < 180) { say('Enlarge Lab before docking a window.'); return; }
    // Create during the click. Detach the opener before any external page is loaded.
    const popup = window.open('about:blank', '_blank', `popup,width=${Math.round(r.width)},height=${Math.round(r.height - 40)},left=${screenX + Math.round(r.left)},top=${screenY + Math.round(outerHeight - innerHeight + r.top)}`);
    if (!popup) { say('Allow pop-ups for Lab, then click Dock again.'); return; }
    popup.opener = null;
    popup.document.title = 'Lab dock popup ' + owner;
    popup.document.body.textContent = 'Aligning this window with Lab…';
    const policy = popup.document.createElement('meta');
    policy.name = 'referrer'; policy.content = 'no-referrer'; popup.document.head.append(policy);
    originalTitle = document.title; marking = true; document.title = 'Lab dock parent ' + owner;
    busy = true; buttons(); say('Identifying and aligning the two windows…');
    try {
      // Allow Chrome to publish the blank page's accessible title.
      await new Promise(resolve => setTimeout(resolve, 250));
      const result = await command('attach', {slot:rectangle(), visible:true});
      if (!result.ok || !result.active) throw Error(result.detail || 'Could not dock this popup.');
      active = true;
      const link = popup.document.createElement('a');
      link.href = url.href; link.rel = 'noreferrer'; popup.document.body.append(link); link.click();
      say('Docked. Try moving/resizing Lab, clicking its controls, and switching apps. Detach keeps the site open.');
      void heartbeat();
    } catch (error) {
      // The only close here targets our still-blank, newly created popup.
      try { popup.close(); } catch {}
      await command('detach').catch(() => {});
      stop(); say(error.message);
    } finally { restoreTitle(); busy = false; buttons(); }
  }
  async function end(operation = 'detach') {
    if (busy) return;
    busy = true; buttons(); clearTimeout(timer);
    try {
      const result = await command(operation);
      say(result.detail);
      if (!result.active) stop();
      else timer = setTimeout(heartbeat, 1000);
    } catch (error) { say(error.message); if (active) timer = setTimeout(heartbeat, 1000); }
    finally { busy = false; buttons(); }
  }
  function open(host) {
    if (panel?.isConnected) return;
    if (!window.LAB_NATIVE_BROWSER_REUSE) return;
    sourceHost = host; owner = crypto.randomUUID().replaceAll('-', '');
    panel = document.createElement('section');
    panel.className = 'lab-window-dock'; panel.setAttribute('aria-label', 'Docked window prototype');
    panel.innerHTML = `<div class="lab-window-dock-heading"><strong>Docked window · Mac prototype</strong><button type="button" data-dock-dismiss>Exit trial</button></div>
      <div class="lab-window-dock-controls"><input type="url" data-dock-url aria-label="Docked website URL" value="https://example.com/">
      <button type="button" data-dock-permission>Enable window control</button><button type="button" data-dock-check>Check permission</button>
      <button type="button" data-dock-start disabled>Dock</button><button type="button" data-dock-detach disabled>Detach</button><button type="button" data-dock-close disabled>Close popup</button></div>
      <p data-dock-status role="status"></p><div data-dock-slot><p>Your real Chrome window will sit here.<br>Its frame remains visible. Nothing is embedded or proxied.</p></div>`;
    document.body.append(panel);
    find('start').onclick = start;
    find('permission').onclick = () => check('permission');
    find('check').onclick = () => check();
    find('detach').onclick = () => end();
    find('close').onclick = () => end('close');
    find('dismiss').onclick = async () => {
      if (busy) return;
      if (active) await end();
      if (active) return;
      panel.remove(); panel = null;
    };
    void check();
  }
  window.addEventListener('pagehide', () => {
    if (active && owner) navigator.sendBeacon('/api/ui/window-dock', new Blob([JSON.stringify({owner, operation:'detach'})], {type:'application/json'}));
  });
  window.LabWindowDock = {open};
})();
