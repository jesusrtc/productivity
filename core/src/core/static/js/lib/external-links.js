// Shared by document, notebook, sidebar, and Assistant links, including HTML
// previews. Resource links have independent windows owned by this Lab window.
(function () {
  'use strict';
  const boundDocuments = new WeakSet();
  const resources = new Map();
  const storageKey = 'lab.resourceWindows.v1';
  function windowToken() {
    if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  let owner = windowToken(), nativeDetail = '', nativeTrusted = true, raising = false;
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey));
    if (saved?.owner) owner = saved.owner;
    for (const item of saved?.resources || []) {
      if (webUrl(item.url)) resources.set(item.url, {native:!!item.native, handle:null});
    }
  } catch {}
  const nativeWindows = () => !!window.LAB_NATIVE_BROWSER_REUSE && /Macintosh/.test(navigator.userAgent)
    && /Chrome\//.test(navigator.userAgent);
  let resourceButton = null;

  function rememberResources() {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({owner,
        resources:[...resources].map(([url, entry]) => ({url, native:entry.native}))}));
    } catch {}
    if (!resourceButton) {
      const topbar = document.querySelector('.topbar');
      if (topbar) {
        resourceButton = document.createElement('button');
        resourceButton.type = 'button'; resourceButton.className = 'resource-windows-button';
        resourceButton.addEventListener('click', showResourceWindows);
        topbar.append(resourceButton);
      }
    }
    if (resourceButton) {
      resourceButton.hidden = !resources.size;
      resourceButton.textContent = `⧉ ${resources.size}`;
      resourceButton.title = 'Resource windows — activate or close';
      resourceButton.setAttribute('aria-label', `Resource windows (${resources.size})`);
    }
  }

  async function nativeAction(operation, values = {}) {
    const response = await fetch('/api/ui/resource-windows', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({owner, operation, ...values}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      if (data.trusted === false) nativeTrusted = false;
      nativeDetail = data.detail || 'Could not control resource windows.';
      throw Error(nativeDetail);
    }
    nativeTrusted = data.trusted !== false;
    nativeDetail = nativeTrusted ? '' : 'Enable Lab Resource Windows in macOS Accessibility.';
    return data;
  }

  function resourceDialog(message, actionText, action) {
    const dialog = document.createElement('dialog');
    dialog.className = 'resource-windows-dialog';
    const text = document.createElement('p'); text.textContent = message;
    const button = document.createElement('button'); button.type = 'button'; button.textContent = actionText;
    button.onclick = () => { dialog.close(); void action(); };
    const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close';
    close.onclick = () => dialog.close();
    dialog.addEventListener('close', () => dialog.remove());
    dialog.append(text, button, close); document.body.append(dialog); dialog.showModal();
  }

  function showResourceWindows() {
    const dialog = document.createElement('dialog'); dialog.className = 'resource-windows-dialog';
    const title = document.createElement('strong'); title.textContent = 'Resource windows'; dialog.append(title);
    const status = document.createElement('p'); status.textContent = nativeDetail; dialog.append(status);
    for (const [url, entry] of resources) {
      const row = document.createElement('div'); row.className = 'resource-window-row';
      const activate = document.createElement('button'); activate.type = 'button';
      activate.textContent = url; activate.title = 'Activate this window';
      activate.onclick = () => { dialog.close(); void openResource(url); };
      const canClose = entry.native || (entry.handle && !entry.handle.closed);
      const close = document.createElement('button'); close.type = 'button'; close.textContent = canClose ? '×' : 'Remove';
      close.setAttribute('aria-label', canClose ? `Close ${url}` : `Remove ${url} from this list`);
      close.onclick = async () => {
        try {
          if (entry.handle && !entry.handle.closed) entry.handle.close();
          else if (entry.native && nativeWindows()) await nativeAction('close', {url});
          resources.delete(url); rememberResources(); row.remove();
        } catch (error) { status.textContent = error.message; }
      };
      row.append(activate, close); dialog.append(row);
    }
    if (nativeWindows()) {
      const setup = document.createElement('button'); setup.type = 'button'; setup.textContent = 'Enable window control';
      setup.onclick = async () => {
        try {
          const result = await nativeAction('permission');
          status.textContent = result.trusted ? 'Window control is enabled.'
            : 'Turn on Lab Resource Windows in Accessibility, then reopen your resource windows.';
        } catch (error) { status.textContent = error.message; }
      };
      dialog.append(setup);
    }
    const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Done';
    close.onclick = () => dialog.close(); dialog.append(close);
    dialog.addEventListener('close', () => dialog.remove());
    document.body.append(dialog); dialog.showModal();
  }

  function webUrl(value, base = document.baseURI) {
    try {
      const url = new URL(value, base);
      return ['http:', 'https:'].includes(url.protocol) ? url : null;
    } catch { return null; }
  }

  function showFallback(url, messageText = 'Could not open your default browser.') {
    const dialog = document.createElement('dialog');
    const message = document.createElement('p');
    message.textContent = messageText;
    const link = document.createElement('a');
    link.textContent = 'Open link in a browser tab';
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.dataset.labBrowserFallback = 'true';
    const close = document.createElement('button');
    close.textContent = 'Close';
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => dialog.remove());
    dialog.append(message, link, document.createTextNode(' '), close);
    document.body.append(dialog);
    dialog.showModal();
  }

  function popupBounds() {
    const slot = resources.size % Math.max(1, Math.floor((window.outerHeight - 360) / 36));
    const offset = Math.round(Math.min(slot * 12, 72, window.outerWidth * .04));
    const left = Math.round(window.screenX + 12 + offset);
    const top = Math.round(window.screenY + 56 + slot * 36);
    const width = Math.max(320, window.outerWidth - 24 - offset);
    const height = Math.max(320, window.outerHeight - 72 - slot * 36);
    return [left, top, width, height];
  }

  async function createResource(url) {
    const bounds = popupBounds(), [left, top, width, height] = bounds;
    // Capture a blank window during the actual click, then immediately detach
    // its opener before any external content can load. Keeping our WindowProxy
    // permits direct user-click focus without giving the resource access to Lab.
    const handle = window.open('about:blank', '_blank', `popup,width=${width},height=${height},left=${left},top=${top}`);
    if (!handle) {
      resourceDialog('Allow pop-ups for Lab to open this resource.', 'Open resource window', () => createResource(url));
      return false;
    }
    const entry = {handle, native:false, pending:null};
    resources.set(url, entry); rememberResources();
    const marker = `Lab resource ${windowToken()}`;
    try {
      handle.sessionStorage?.removeItem(storageKey);
      handle.opener = null;
      const policy = handle.document.createElement('meta');
      policy.name = 'referrer'; policy.content = 'no-referrer'; handle.document.head.append(policy);
      handle.document.title = marker;
      handle.document.body.textContent = 'Opening resource…';
    } catch {
      handle.close(); resources.delete(url); rememberResources(); return false;
    }
    entry.pending = Promise.resolve().then(async () => {
      if (nativeWindows()) {
        try {
          await nativeAction('register', {url, marker, bounds,
            parentBounds:[window.screenX, window.screenY, window.outerWidth, window.outerHeight]});
          entry.native = true;
        } catch {} // The direct client window still works when control is unavailable.
      }
      if (!handle.closed) {
        const destination = handle.document.createElement('a');
        destination.href = url; destination.rel = 'noreferrer'; destination.referrerPolicy = 'no-referrer';
        handle.document.body.append(destination); destination.click();
      }
      rememberResources();
      return true;
    }).finally(() => { entry.pending = null; });
    return entry.pending;
  }

  async function openResource(url) {
    const entry = resources.get(url);
    if (!entry) return createResource(url);
    if (entry.handle && !entry.handle.closed) {
      entry.handle.focus();
      if (entry.native && nativeWindows() && !entry.pending) {
        try { await nativeAction('focus', {url}); } catch {}
      }
      return true;
    }
    if (entry.pending) return entry.pending;
    if (entry.native && nativeWindows()) {
      try {
        const result = await nativeAction('focus', {url});
        if (result.reused) return true;
        // The helper confirmed that the captured native window has closed.
        resources.delete(url); rememberResources(); return createResource(url);
      } catch (error) {
        resourceDialog(error.message, 'Retry activation', () => openResource(url)); return false;
      }
    }
    // COOP can sever a reference while the resource is still open. A `closed`
    // WindowProxy alone is not evidence that creating a duplicate is safe.
    resourceDialog('This window can no longer be activated from the browser. Enable window control or use its title bar.',
      'Open another window', () => { resources.delete(url); rememberResources(); void createResource(url); });
    return false;
  }

  async function raiseResources(explicit = false) {
    if (!resources.size || raising || document.visibilityState !== 'visible') return;
    raising = true;
    try {
      if (nativeWindows()) {
        const result = await nativeAction('raise');
        for (const [url, entry] of resources) {
          if (entry.native && !result.urls.includes(url) && !entry.pending) resources.delete(url);
        }
        rememberResources();
      } else {
        for (const entry of resources.values()) if (entry.handle && !entry.handle.closed) entry.handle.focus();
      }
    } catch (error) { if (explicit) showResourceWindows(); }
    finally { raising = false; }
  }

  async function open(value, {clientOnly = false, reuseTab = false, popup = false} = {}) {
    const url = webUrl(value);
    if (!url) return false;
    if (popup) {
      return openResource(url.href);
    }
    // Explicit workspace browser opening can use the local Mac's default
    // browser tab search. Remote clients keep their ordinary browser opening.
    if (reuseTab && window.LAB_NATIVE_BROWSER_REUSE) {
      try {
        const response = await fetch('/api/ui/open-external', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({url:url.href, reuse_existing:true}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
          throw new Error(data.detail || 'Could not reuse your browser tab.');
        }
        return true;
      } catch (error) {
        showFallback(url.href, error.message || 'Could not reuse your browser tab.');
        return false;
      }
    }
    // A remote browser must open its own tab, never the server's desktop.
    if (clientOnly || !window.LAB_EXTERNAL_BROWSER) {
      window.open(url.href, '_blank', 'noopener,noreferrer');
      return true;
    }
    try {
      const response = await fetch('/api/ui/open-external', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url.href}),
      });
      if (!response.ok) throw new Error('Browser opening failed');
      return true;
    } catch {
      // A fresh user click keeps the fallback usable with popup blockers.
      showFallback(url.href);
      return false;
    }
  }

  function onLink(event) {
    if (event.defaultPrevented || (event.type === 'click' ? event.button !== 0 : event.button !== 1)) return;
    const link = event.target.closest?.('a[href], area[href]');
    if (!link || link.hasAttribute('download') || link.hasAttribute('data-lab-browser-fallback')) return;
    const url = webUrl(link.getAttribute('href'), link.ownerDocument.baseURI);
    if (!url || url.origin === window.location.origin) return;
    event.preventDefault();
    event.stopPropagation();
    void open(url.href, {clientOnly:link.hasAttribute('data-lab-client-external')});
  }

  function bindFrame(frame) {
    try { if (frame.contentDocument) bindDocument(frame.contentDocument); }
    catch {} // Cross-origin embeds retain their own browser security boundary.
  }

  function bindDocument(doc) {
    if (boundDocuments.has(doc)) return;
    boundDocuments.add(doc);
    // Capture before document expansion and embedded app click handlers.
    doc.addEventListener('click', onLink, true);
    doc.addEventListener('auxclick', onLink, true);
    doc.addEventListener('load', event => {
      if (event.target.tagName === 'IFRAME') bindFrame(event.target);
    }, true);
    doc.querySelectorAll('iframe').forEach(bindFrame);
  }

  window.LabExternalLinks = {open, raiseResources};
  bindDocument(document);
  rememberResources();
  window.addEventListener('focus', () => { void raiseResources(); });
  document.addEventListener('click', event => {
    if (event.isTrusted && event.target.closest?.('.topbar, #repoTabs')
        && !event.target.closest('.resource-windows-button, input, select')) void raiseResources();
  });
})();
