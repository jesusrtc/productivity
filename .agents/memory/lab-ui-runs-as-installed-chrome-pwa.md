---
name: lab-ui-runs-as-installed-chrome-pwa
description: "User runs the lab UI as an installed Chrome PWA, so same-origin window.open opens frameless app windows (no URL bar)"
metadata:
  node_type: memory
  type: project
  originSessionId: 5b94e40b-5dd8-4e4a-9cb8-4dfaaea247e5
---

The user opens the lab UI (`core`, `templates/index.html`, served at the
port in `.lab-server.port` — 8080 as of 2026-05-29) as an **installed Chrome app
(PWA)**, not a normal browser tab. There is no web manifest/service worker; Chrome
just "Install as app", so the app scope is the lab origin.

**Why:** Inside an installed PWA, `window.open(url, '_blank')` to a **same-origin**
URL opens a frameless standalone app window with **no address bar** ("weird popup").
Only a URL on a **different origin** (out of PWA scope) opens in a normal Chrome
browser window *with* the URL bar.

**How to apply:** For any "open in new window/tab" UI, prefer a cross-origin /
direct URL over a same-origin one. Concretely, the per-project dev-server "Pop out"
(`openProjectProxyTab`) now opens the **direct `http://host:port/...`** URL via the
`_proxyDirectUrl()` helper instead of the same-origin `/api/proxy/<id>/<name>/`
mount. Tradeoff: the direct port must be reachable from the browser, so this
pop-out won't work over an SSH forward that exposes only the lab port (fine for
local use). The inline iframe still uses the proxy mount.
