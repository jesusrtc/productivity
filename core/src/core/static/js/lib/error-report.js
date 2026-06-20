/**
 * error-report.js — client-side error capture → server upload.
 *
 * Hooks window.onerror, unhandledrejection, and wraps console.error /
 * console.warn to also POST captured events to /api/log/client.
 *
 * Batching: events are queued and flushed either after 250ms of inactivity
 * or when the queue reaches 50 items, whichever comes first.
 *
 * Loaded as <script defer> so it installs after the page's synchronous
 * inline error handlers but before any deferred app code runs.
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/log/client';
  var DEBOUNCE_MS = 250;
  var MAX_BATCH = 50;
  var MAX_MSG_LEN = 2000;
  var MAX_QUEUE = MAX_BATCH * 4; // hard cap to prevent memory leak on rapid errors

  var _queue = [];
  var _timer = null;

  /** POST a batch of events to the server. Best-effort — never throws. */
  function _flush() {
    _timer = null;
    if (!_queue.length) return;
    var batch = _queue.splice(0, MAX_BATCH);
    try {
      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events: batch }),
        keepalive: true,  // survives page unload
      }).catch(function () {});
    } catch (_) {}
  }

  /** Add one event to the queue; flush immediately if full, else debounce. */
  function _enqueue(level, msg, path) {
    if (_queue.length >= MAX_QUEUE) return;
    _queue.push({
      level: level,
      msg: String(msg).slice(0, MAX_MSG_LEN),
      path: path || window.location.pathname,
    });
    if (_queue.length >= MAX_BATCH) {
      if (_timer !== null) { clearTimeout(_timer); _timer = null; }
      _flush();
    } else {
      if (_timer !== null) clearTimeout(_timer);
      _timer = setTimeout(_flush, DEBOUNCE_MS);
    }
  }

  // ── window.onerror ──────────────────────────────────────────────────────────
  var _prevOnError = window.onerror;
  window.onerror = function (msg, src, line, col, err) {
    var detail = String(msg || 'error');
    if (err && err.stack) detail += '\n' + err.stack;
    _enqueue('error', detail, (src || '') + ':' + (line || '?'));
    if (typeof _prevOnError === 'function') {
      return _prevOnError.apply(this, arguments);
    }
    return false;
  };

  // ── unhandled promise rejections ────────────────────────────────────────────
  window.addEventListener('unhandledrejection', function (ev) {
    var reason = ev.reason;
    var msg = reason instanceof Error
      ? reason.message + (reason.stack ? '\n' + reason.stack : '')
      : 'Unhandled rejection: ' + String(reason);
    _enqueue('error', msg, window.location.pathname);
  });

  // ── console.error / console.warn wrappers ───────────────────────────────────
  ['error', 'warn'].forEach(function (method) {
    var _orig = console[method].bind(console);
    console[method] = function () {
      // Always call the original so DevTools output is unchanged.
      _orig.apply(console, arguments);
      // Collect args into a single string for the log entry.
      var parts = Array.prototype.slice.call(arguments).map(function (a) {
        if (a instanceof Error) return a.message + (a.stack ? '\n' + a.stack : '');
        if (typeof a === 'object') { try { return JSON.stringify(a); } catch (_) {} }
        return String(a);
      });
      _enqueue(method === 'error' ? 'error' : 'warning', parts.join(' '), window.location.pathname);
    };
  });
})();
