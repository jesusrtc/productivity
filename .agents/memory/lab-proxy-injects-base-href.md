---
name: lab-proxy-injects-base-href
description: Lab per-project proxy injects <base href> into HTML — pages in subdirectories break unless they declare their own <base> tag
metadata:
  node_type: memory
  type: project
  originSessionId: 5986449f-28bf-4032-b83a-175f437ffe0d
---

The lab server's per-project reverse proxy (`core/src/core/routes/proxy.py`, mount `/api/proxy/<project>/<name>/`) injects `<base href="<mount-root>">` into every proxied HTML page. For pages living in a subdirectory, this rewrites all relative URLs to resolve against the site root, 404ing their CSS/JS and making `../` links escape the proxy mount (error: "proxy '<segment>' not declared in project ...").

**Why:** the injection helps root-relative SPAs but breaks plain multi-page static sites with document-relative links.

**How to apply:** the injection is skipped when the page already has a `<base ` tag in its first 4KB — add `<base target="_self">` to the `<head>` of every page of a static site that will be viewed through the lab proxy. Used in [[lab-ui-runs-as-installed-chrome-pwa]] context for the pytype prototypes in `projects/programming/`.
