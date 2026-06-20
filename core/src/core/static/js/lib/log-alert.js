(function () {
  const STATE_URL = "/api/log/error-state";
  const LOG_URL = "/logs?file=errors.log&tail=500";
  const STORAGE_KEY = "lab.errorLog.seenCursor";
  const POLL_MS = 15000;

  let button = null;
  let latestState = null;
  let timer = null;

  function injectStyle() {
    if (document.getElementById("lab-log-alert-style")) return;
    const style = document.createElement("style");
    style.id = "lab-log-alert-style";
    style.textContent = `
      .lab-log-alert {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        min-height: 30px;
        padding: 4px 10px;
        border: 1px solid var(--border, #bbb);
        border-radius: 6px;
        background: var(--bg-tertiary, #f5f5f5);
        color: var(--text-secondary, #555);
        font: 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        text-decoration: none;
        cursor: pointer;
        white-space: nowrap;
      }
      .lab-log-alert:hover {
        color: var(--text-primary, #111);
        background: var(--border, #e8e8e8);
        text-decoration: none;
      }
      .lab-log-alert.has-unseen {
        background: #da3633;
        border-color: #f85149;
        color: #fff;
        box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.18);
      }
      .lab-log-alert.has-unseen:hover {
        background: #f85149;
        color: #fff;
      }
      .lab-log-alert .lab-log-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: currentColor;
        display: none;
      }
      .lab-log-alert.has-unseen .lab-log-dot {
        display: inline-block;
      }
      .lab-log-alert-floating {
        position: fixed;
        right: 14px;
        bottom: 14px;
        z-index: 5000;
      }
    `;
    document.head.appendChild(style);
  }

  function seenCursor() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch {
      return "";
    }
  }

  function setSeenCursor(cursor) {
    if (!cursor) return;
    try {
      localStorage.setItem(STORAGE_KEY, cursor);
    } catch {}
  }

  function hasUnseen(state) {
    if (!state || !state.exists || !state.size || !state.cursor) return false;
    return seenCursor() !== state.cursor;
  }

  function renderButtonState() {
    if (!button) return;
    const unseen = hasUnseen(latestState);
    button.classList.toggle("has-unseen", unseen);
    button.title = unseen
      ? "New errors since you last opened the error log"
      : "Open error logs";
    const label = button.querySelector(".lab-log-label");
    if (label) label.textContent = unseen ? "Errors: new" : "Errors";
  }

  function ensureButton() {
    if (button) return button;
    injectStyle();

    button = document.getElementById("labLogAlertButton");
    if (!button) {
      button = document.createElement("a");
      button.id = "labLogAlertButton";
      button.className = "lab-log-alert";
      button.href = LOG_URL;
      button.innerHTML = '<span class="lab-log-dot"></span><span class="lab-log-label">Errors</span>';

      const topbar = document.querySelector(".topbar");
      const settings = document.getElementById("settingsBtn");
      if (topbar && settings && settings.parentElement === topbar) {
        topbar.insertBefore(button, settings);
      } else if (topbar) {
        topbar.appendChild(button);
      } else {
        const nav = document.querySelector("header nav");
        if (nav) {
          nav.appendChild(button);
        } else {
          button.classList.add("lab-log-alert-floating");
          document.body.appendChild(button);
        }
      }
    }

    return button;
  }

  async function refresh() {
    ensureButton();
    try {
      const response = await fetch(STATE_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      latestState = await response.json();
      renderButtonState();
    } catch {
      if (button) {
        button.classList.remove("has-unseen");
        button.title = "Error log status unavailable";
      }
    }
  }

  function markSeen(state) {
    const cursor = state && state.cursor ? state.cursor : latestState && latestState.cursor;
    setSeenCursor(cursor);
    renderButtonState();
  }

  function start() {
    ensureButton();
    refresh();
    if (timer) clearInterval(timer);
    timer = setInterval(refresh, POLL_MS);
  }

  window.labLogAlertRefresh = refresh;
  window.labLogAlertMarkSeen = markSeen;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
  window.addEventListener("hashchange", refresh);
})();
