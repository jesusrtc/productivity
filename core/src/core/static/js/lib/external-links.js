// Shared by document, notebook, sidebar, and Assistant links, including HTML
// previews. A local PWA hands URLs to the OS instead of opening another app window.
(function () {
  'use strict';
  const boundDocuments = new WeakSet();

  function webUrl(value, base = document.baseURI) {
    try {
      const url = new URL(value, base);
      return ['http:', 'https:'].includes(url.protocol) ? url : null;
    } catch { return null; }
  }

  function showFallback(url) {
    const dialog = document.createElement('dialog');
    const message = document.createElement('p');
    message.textContent = 'Could not open your default browser.';
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

  async function open(value) {
    const url = webUrl(value);
    if (!url) return false;
    // A remote browser must open its own tab, never the server's desktop.
    if (!window.LAB_EXTERNAL_BROWSER) {
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
    void open(url.href);
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
