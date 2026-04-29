import { subscribeWS } from "./api.js";
import { clear } from "./lib/dom.js";

// Dynamic imports keep each view's code out of the initial bundle.
const routes = [
  { pattern: /^\/?$/, loader: () => import("./views/dashboard.js") },
  { pattern: /^\/p\/([^/]+)$/, loader: () => import("./views/project.js") },
  { pattern: /^\/timeline$/, loader: () => import("./views/timeline.js") },
  { pattern: /^\/md$/, loader: () => import("./views/markdown.js") },
  { pattern: /^\/nb$/, loader: () => import("./views/notebook.js") },
  { pattern: /^\/search$/, loader: () => import("./views/search.js") },
];

let currentRender = null;

async function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const [path, query] = hash.split("?");
  const params = new URLSearchParams(query || "");

  const view = document.getElementById("view");
  for (const { pattern, loader } of routes) {
    const match = path.match(pattern);
    if (match) {
      const mod = await loader();
      clear(view);
      currentRender = () => mod.render(view, { match, params });
      currentRender();
      return;
    }
  }

  clear(view);
  view.textContent = `No route for ${path}`;
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  route();
  // Dedupe identical `index-updated` bursts: the watcher can fire multiple
  // times per logical change (e.g. write + fsync). Only re-render when the
  // event timestamp actually advances.
  let lastTs = null;
  subscribeWS((event) => {
    if (event.type !== "index-updated" || !currentRender) return;
    if (event.ts && event.ts === lastTs) return;
    lastTs = event.ts;
    currentRender();
  });
});
