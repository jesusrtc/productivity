/**
 * Browser log capture -> /api/log/client.
 *
 * Captures:
 *   - window errors and unhandled promise rejections
 *   - console.error / console.warn
 *   - fetch calls to backend services
 *   - user actions: click, submit, change, keyboard activation
 *   - route/page lifecycle events
 *
 * The upload path uses the native fetch captured at startup so logging the
 * logging endpoint never recurses through the fetch wrapper.
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/log/client';
  var DEBOUNCE_MS = 250;
  var MAX_BATCH = 50;
  var MAX_MSG_LEN = 2000;
  var MAX_FIELD_LEN = 500;
  var MAX_QUEUE = MAX_BATCH * 8;

  var _nativeFetch = typeof window.fetch === 'function'
    ? window.fetch.bind(window)
    : null;
  var _queue = [];
  var _timer = null;

  function _now() {
    return (window.performance && typeof window.performance.now === 'function')
      ? window.performance.now()
      : Date.now();
  }

  function _currentPath() {
    var loc = window.location || {};
    return String((loc.pathname || '/') + (loc.search || '') + (loc.hash || ''));
  }

  function _limit(v, n) {
    if (v == null) return undefined;
    var s = String(v);
    return s.length > n ? s.slice(0, n) : s;
  }

  function _event(level, msg, details) {
    details = details || {};
    var ev = {
      level: level || 'info',
      msg: _limit(msg || details.action || 'client event', MAX_MSG_LEN),
      path: _limit(details.path || _currentPath(), MAX_FIELD_LEN),
    };
    [
      'action',
      'target',
      'event_type',
      'href',
      'method',
      'source_url',
    ].forEach(function (k) {
      if (details[k] != null) ev[k] = _limit(details[k], MAX_FIELD_LEN);
    });
    if (details.status_code != null) ev.status_code = Number(details.status_code);
    if (details.duration_ms != null) ev.duration_ms = Number(details.duration_ms);
    return ev;
  }

  function _flush(useBeacon) {
    _timer = null;
    if (!_queue.length) return;
    var batch = _queue.splice(0, MAX_BATCH);
    var payload = JSON.stringify({ events: batch });
    try {
      if (useBeacon && navigator && typeof navigator.sendBeacon === 'function') {
        var blob = new Blob([payload], { type: 'application/json' });
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      }
    } catch (_) {}
    if (!_nativeFetch) return;
    try {
      _nativeFetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
      }).catch(function () {});
    } catch (_) {}
  }

  function _enqueue(level, msg, details, immediate) {
    if (_queue.length >= MAX_QUEUE) return;
    _queue.push(_event(level, msg, details));
    if (immediate || _queue.length >= MAX_BATCH) {
      if (_timer !== null) {
        clearTimeout(_timer);
        _timer = null;
      }
      _flush(false);
      return;
    }
    if (_timer !== null) clearTimeout(_timer);
    _timer = setTimeout(function () { _flush(false); }, DEBOUNCE_MS);
  }

  function _describeElement(el) {
    if (!el) return '';
    var bits = [];
    var tag = (el.tagName || '').toLowerCase();
    if (tag) bits.push(tag);
    var id = el.getAttribute && el.getAttribute('id');
    if (id) bits.push('#' + id);
    var name = el.getAttribute && (el.getAttribute('name') || el.getAttribute('aria-label') || el.getAttribute('title'));
    var action = el.getAttribute && (el.getAttribute('data-log-action') || el.getAttribute('data-act') || el.getAttribute('data-mode'));
    var text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    if (action) bits.push('[' + action + ']');
    if (name) bits.push('"' + name + '"');
    else if (text) bits.push('"' + text.slice(0, 80) + '"');
    return _limit(bits.join(' '), MAX_FIELD_LEN) || tag || 'element';
  }

  function _closestActionTarget(target) {
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest('button,a,[role="button"],summary,[data-log-action],[data-act],[data-mode]');
  }

  function _logDomAction(action, nativeEvent, target, immediate) {
    target = target || (nativeEvent && nativeEvent.target);
    if (!target) return;
    var href = target.getAttribute && target.getAttribute('href');
    _enqueue('info', 'client action: ' + action, {
      action: action,
      event_type: nativeEvent && nativeEvent.type,
      target: _describeElement(target),
      href: href || undefined,
    }, immediate);
  }

  window.labLog = {
    log: _enqueue,
    info: function (msg, details) { _enqueue('info', msg, details); },
    warning: function (msg, details) { _enqueue('warning', msg, details); },
    error: function (msg, details) { _enqueue('error', msg, details, true); },
    action: function (name, details) {
      details = details || {};
      details.action = details.action || name;
      _enqueue('info', 'client action: ' + name, details);
    },
    flush: function () { _flush(false); },
  };

  // Window errors.
  var _prevOnError = window.onerror;
  window.onerror = function (msg, src, line, col, err) {
    var detail = String(msg || 'error');
    if (err && err.stack) detail += '\n' + err.stack;
    _enqueue('error', detail, {
      action: 'window.onerror',
      source_url: (src || '') + ':' + (line || '?') + ':' + (col || '?'),
    }, true);
    if (typeof _prevOnError === 'function') {
      return _prevOnError.apply(this, arguments);
    }
    return false;
  };

  window.addEventListener('unhandledrejection', function (ev) {
    var reason = ev.reason;
    var msg = reason instanceof Error
      ? reason.message + (reason.stack ? '\n' + reason.stack : '')
      : 'Unhandled rejection: ' + String(reason);
    _enqueue('error', msg, { action: 'unhandledrejection' }, true);
  });

  // Console warnings/errors.
  ['error', 'warn'].forEach(function (method) {
    var orig = console[method] && console[method].bind(console);
    if (!orig) return;
    console[method] = function () {
      orig.apply(console, arguments);
      var parts = Array.prototype.slice.call(arguments).map(function (a) {
        if (a instanceof Error) return a.message + (a.stack ? '\n' + a.stack : '');
        if (typeof a === 'object') {
          try { return JSON.stringify(a); } catch (_) {}
        }
        return String(a);
      });
      _enqueue(method === 'error' ? 'error' : 'warning', parts.join(' '), {
        action: 'console.' + method,
      }, method === 'error');
    };
  });

  // Backend API/service calls.
  if (_nativeFetch) {
    window.fetch = function (input, opts) {
      opts = opts || {};
      var started = _now();
      var method = (opts.method || (input && input.method) || 'GET').toUpperCase();
      var url = (typeof input === 'string') ? input : (input && input.url) || '';
      var path;
      try {
        path = new URL(url, window.location && window.location.href || 'http://localhost/').pathname;
      } catch (_) {
        path = String(url || '');
      }
      if (path === ENDPOINT) {
        return _nativeFetch(input, opts);
      }
      return _nativeFetch(input, opts).then(function (resp) {
        var duration = Math.round((_now() - started) * 100) / 100;
        var status = resp && resp.status;
        var level = status >= 500 ? 'error' : (status >= 400 ? 'warning' : 'info');
        _enqueue(level, 'frontend fetch ' + method + ' ' + path + ' -> ' + status, {
          action: 'fetch',
          method: method,
          status_code: status,
          duration_ms: duration,
          target: path,
          href: url,
        }, level === 'error');
        return resp;
      }, function (err) {
        var duration = Math.round((_now() - started) * 100) / 100;
        _enqueue('warning', 'frontend fetch ' + method + ' ' + path + ' failed: ' + (err && err.message || err), {
          action: 'fetch',
          method: method,
          duration_ms: duration,
          target: path,
          href: url,
        }, false);
        throw err;
      });
    };
  }

  // User actions.
  document.addEventListener('click', function (ev) {
    var target = _closestActionTarget(ev.target);
    if (!target) return;
    _logDomAction('click', ev, target, target.tagName === 'A');
  }, true);

  document.addEventListener('submit', function (ev) {
    _logDomAction('submit', ev, ev.target, true);
  }, true);

  document.addEventListener('change', function (ev) {
    var target = ev.target;
    if (!target || !/^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName || '')) return;
    _logDomAction('change', ev, target, false);
  }, true);

  document.addEventListener('keydown', function (ev) {
    if (!(ev.key === 'Enter' || ev.key === ' ')) return;
    var target = _closestActionTarget(ev.target);
    if (!target) return;
    _logDomAction('keyboard-activate', ev, target, false);
  }, true);

  window.addEventListener('hashchange', function () {
    _enqueue('info', 'client route change', { action: 'route.hashchange' });
  });
  window.addEventListener('popstate', function () {
    _enqueue('info', 'client route change', { action: 'route.popstate' });
  });
  window.addEventListener('pagehide', function () { _flush(true); });
})();
