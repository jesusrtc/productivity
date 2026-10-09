/* Browser-only mock state. The sandbox never calls workspace or terminal APIs. */
(() => {
  const channel = 'lab-objectives-demo-v1';
  const storageKey = 'labObjectivesDemo:v1';
  const ownScript = document.currentScript;
  const version = ownScript ? new URL(ownScript.src).searchParams.get('v') : '';
  let frame = null;

  window.addEventListener('message', event => {
    if (!frame?.isConnected || event.source !== frame.contentWindow
        || event.data?.channel !== channel) return;
    if (event.data.type === 'ready') {
      let state = null;
      try { state = JSON.parse(localStorage.getItem(storageKey)); } catch {}
      frame.contentWindow.postMessage({channel, type: 'hydrate', state}, '*');
    } else if (event.data.type === 'save' && event.data.state?.version === 1) {
      try {
        const serialized = JSON.stringify(event.data.state);
        if (serialized.length <= 750000) localStorage.setItem(storageKey, serialized);
      } catch {}
    }
  });

  function open(host) {
    frame = document.createElement('iframe');
    frame.className = 'objectives-demo-frame';
    frame.title = 'Interactive objectives demo — simulated files and terminals';
    frame.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox');
    frame.src = '/static/demos/objectives/index.html' + (version ? '?v=' + encodeURIComponent(version) : '');
    host.replaceChildren(frame);
  }

  window.LabObjectivesDemo = {open};
})();
