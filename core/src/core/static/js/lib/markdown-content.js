/* Shared Markdown rendering and copying. Copy always snapshots the live view. */
(function () {
  function sanitize(html) {
    if (!window.DOMPurify) throw new Error('Markdown sanitizer is not loaded');
    return DOMPurify.sanitize(html, {
      FORBID_TAGS: ['style', 'form'],
      FORBID_ATTR: ['style', 'srcdoc'],
      ALLOW_DATA_ATTR: false,
    });
  }

  function render(markdown, options) {
    return sanitize(window.marked.parse(markdown, options));
  }

  function cloneVisible(root, {heading, includeHeading = true} = {}) {
    const clone = document.createElement('div');
    if (heading) {
      if (!root.contains(heading) || heading.closest('details:not([open])')) return clone;
      // Headings in disclosures belong to that disclosure, not the outer section.
      const scope = heading.closest('details') || root;
      const level = Number(heading.tagName.slice(1));
      const headings = Array.from(scope.querySelectorAll('h1,h2,h3,h4,h5,h6'));
      const next = headings.slice(headings.indexOf(heading) + 1).find(candidate =>
        Number(candidate.tagName.slice(1)) <= level
        && (candidate.closest('details') || root) === scope);
      const range = document.createRange();
      range.selectNodeContents(scope);
      if (includeHeading) range.setStartBefore(heading);
      else range.setStartAfter(heading);
      if (next) range.setEndBefore(next);
      clone.appendChild(range.cloneContents());
    } else {
      clone.append(...Array.from(root.childNodes, node => node.cloneNode(true)));
    }
    // Remove closed parents before flattening open children; never fetch their images.
    clone.querySelectorAll('details:not([open]), [hidden], button, textarea, input, select, form, script, style, iframe, .view-toggle, .assistant-copy-actions, .markdown-copy-action, #commentInputBox, #commentsMargin')
      .forEach(node => node.remove());
    Array.from(clone.querySelectorAll('details')).reverse().forEach(details => {
      const summary = details.querySelector(':scope > summary');
      if (summary) {
        const label = document.createElement('p');
        const strong = document.createElement('strong');
        strong.append(...summary.childNodes);
        label.appendChild(strong);
        summary.replaceWith(label);
      }
      details.replaceWith(...details.childNodes);
    });
    return clone;
  }

  function styleForDocs(clone) {
    clone.removeAttribute('class');
    clone.style.cssText = 'font-family:Arial,sans-serif;color:#000;background:#fff;font-size:11pt;line-height:1.15;';
    clone.querySelectorAll('*').forEach(node => {
      node.removeAttribute('style');
      node.removeAttribute('class');
      node.removeAttribute('id');
    });
    clone.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(node => {
      node.textContent = node.textContent.trim();
      node.style.fontFamily = 'Arial, sans-serif';
    });
    clone.querySelectorAll('p,li,span,div,td,th').forEach(node => {
      if (!node.closest('h1,h2,h3,h4,h5,h6'))
        node.style.cssText = 'font-family:Arial,sans-serif;font-size:11pt;line-height:1.15;color:#000;';
    });
    clone.querySelectorAll('ul,ol').forEach(node => { node.style.paddingLeft = '24pt'; });
    clone.querySelectorAll('code').forEach(node => { node.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;color:#000;'; });
    clone.querySelectorAll('pre').forEach(node => { node.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;padding:8pt;margin:6pt 0;color:#000;white-space:pre-wrap;'; });
    clone.querySelectorAll('a').forEach(node => { node.style.color = '#1155cc'; });
    clone.querySelectorAll('img').forEach(node => { node.style.cssText = 'max-width:100%;height:auto;margin:8pt 0;'; });
    clone.querySelectorAll('table').forEach(node => { node.style.borderCollapse = 'collapse'; });
    clone.querySelectorAll('td,th').forEach(node => {
      node.style.border = '1px solid #ccc';
      node.style.padding = '4pt 6pt';
    });
  }

  async function inlineImages(clone) {
    await Promise.all(Array.from(clone.querySelectorAll('img'), async img => {
      try {
        const response = await fetch(img.src);
        if (!response.ok) return;
        const blob = await response.blob();
        img.src = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(blob);
        });
      } catch (_) { /* Keep the resolved image URL if embedding is unavailable. */ }
    }));
  }

  async function writeClipboard(html, plain, plainOnly) {
    try {
      if (plainOnly) await navigator.clipboard.writeText(plain);
      else await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([html], {type: 'text/html'}),
        'text/plain': new Blob([plain], {type: 'text/plain'}),
      })]);
      return;
    } catch (_) { /* Older browsers or denied rich clipboard access. */ }
    const fallback = document.createElement('textarea');
    fallback.value = plain;
    fallback.style.cssText = 'position:fixed;left:-9999px;top:0;';
    const active = document.activeElement;
    const selection = window.getSelection();
    const ranges = Array.from({length: selection.rangeCount}, (_, i) => selection.getRangeAt(i).cloneRange());
    let supplied = false;
    const onCopy = event => {
      if (!event.clipboardData) return;
      event.preventDefault();
      event.clipboardData.setData('text/plain', plain);
      if (!plainOnly) event.clipboardData.setData('text/html', html);
      supplied = true;
    };
    document.body.appendChild(fallback);
    fallback.select();
    document.addEventListener('copy', onCopy);
    try {
      if (!document.execCommand('copy') || !supplied) throw new Error('Clipboard access failed');
    } finally {
      document.removeEventListener('copy', onCopy);
      fallback.remove();
      if (active && active.isConnected) active.focus({preventScroll: true});
      selection.removeAllRanges();
      ranges.forEach(range => selection.addRange(range));
    }
  }

  async function copy(root, options = {}) {
    if (!root) return false;
    // Snapshot before any asynchronous work, so changing a fold during copying
    // cannot produce different rich-text and plain-text content.
    const clone = cloneVisible(root, options);
    const button = options.button;
    const original = button && button.innerHTML;
    if (button) { button.disabled = true; button.textContent = 'Copying…'; }
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;left:-99999px;top:0;width:900px;pointer-events:none;';
    try {
      styleForDocs(clone);
      if (!options.plainOnly) await inlineImages(clone);
      host.appendChild(clone);
      document.body.appendChild(host);
      const plain = clone.innerText.trim();
      await writeClipboard(clone.outerHTML, plain, options.plainOnly);
      if (button) button.textContent = 'Copied';
      return true;
    } catch (error) {
      if (button) button.textContent = 'Copy failed';
      console.warn('Could not copy document', error);
      return false;
    } finally {
      host.remove();
      if (button) {
        button.disabled = false;
        setTimeout(() => { button.innerHTML = original; }, 1500);
      }
    }
  }

  window.LabMarkdown = {sanitize, render, cloneVisible, copy};
})();
