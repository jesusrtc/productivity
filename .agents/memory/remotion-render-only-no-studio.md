---
name: remotion-render-only-no-studio
description: "User explicitly removed Remotion Studio from projects/remotion (2026-06-10) — render-only workflow; don't reintroduce the Studio or lab-proxy hacks for it"
metadata:
  node_type: memory
  type: feedback
  originSessionId: aba300f4-cf42-408d-959b-5a68da80444b
---

After getting Remotion Studio working through the lab reverse proxy (pushState
patch, SSE streaming, staticBase rewrite in `core/src/core/routes/proxy.py`),
the user decided it wasn't worth it: "olvidemos y deshagamos todo el remotion
studio... solo nos quedamos con el código que hace el renderizado". All proxy
changes were reverted and the Studio server killed.

**Why:** the Studio fought the path-prefix proxy at every step (absolute
asset URLs, URL rewriting, SSE, worker fetches); the render-to-folder flow
covers the actual need (Claude builds the video, user watches the mp4).

**How to apply:** in `projects/remotion`, review videos by rendering
(`npx remotion render <Id> ../out/x.mp4`) or stills — never suggest
launching Remotion Studio or re-adding proxy support for it unless the user
asks. The lab proxy (`core/src/core/routes/proxy.py`) intentionally does NOT
support SPAs that rewrite URLs with absolute paths.
