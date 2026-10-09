// Shared by document, notebook, sidebar, and Assistant links, including HTML
// previews. Resource links open directly on the clicking device.
(function () {
  'use strict';
  const boundDocuments = new WeakSet();
  let popupCount = 0;

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

  function popupFeatures() {
    const slot = popupCount++ % 5;
    const offset = Math.round(Math.min(slot * 12, 72, window.outerWidth * .04));
    const left = Math.round(window.screenX + 12 + offset);
    const top = Math.round(window.screenY + 56 + slot * 36);
    const width = Math.max(320, window.outerWidth - 24 - offset);
    // Feature height is the content height. Reserve the popup's own frame so
    // Chrome does not move an oversized window upwards over Lab's tab strip.
    const height = Math.max(100, window.outerHeight - 172 - slot * 36);
    return `popup,width=${width},height=${height},left=${left},top=${top},noopener,noreferrer`;
  }

  async function open(value, {clientOnly = false, reuseTab = false, popup = false} = {}) {
    const url = webUrl(value);
    if (!url) return false;
    if (popup) {
      window.open(url.href, '_blank', popupFeatures());
      // noopener returns no handle even when opening succeeds.
      return true;
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

  window.LabExternalLinks = {open};
  bindDocument(document);
})();
