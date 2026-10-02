"""Focus an existing default-browser tab on macOS without reloading it.

Adapted from the Chrome tab action in the user's Alfred URL workflow. URL
arguments are data, never interpolated into executable AppleScript/JXA.
"""
import json
import re
import subprocess
import threading
import time
from urllib.parse import parse_qsl, urlsplit


SCRIPT = r'''
function run(argv) {
    ObjC.import('AppKit');
    const target = argv[0], docPrefix = argv[1] || '';
    const appURL = $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL($.NSURL.URLWithString(target));
    if (!appURL) return JSON.stringify({handled:false, reused:false});
    const bundle = ObjC.unwrap($.NSBundle.bundleWithURL(appURL).bundleIdentifier);
    const safari = ['com.apple.Safari', 'com.apple.SafariTechnologyPreview'].includes(bundle);
    const chromium = ['com.google.Chrome', 'com.google.Chrome.beta', 'com.google.Chrome.canary',
        'com.microsoft.edgemac', 'com.brave.Browser', 'org.chromium.Chromium'].includes(bundle);
    if (!safari && !chromium) return JSON.stringify({handled:false, reused:false});
    const app = Application(ObjC.unwrap(appURL.path));
    if (!app.running()) return JSON.stringify({handled:false, reused:false});
    let documentMatch = null;
    function focus(window, tab, index) {
        if (safari) {
            window.currentTab = tab;
            try { window.miniaturized = false; } catch (_) {}
        } else {
            window.activeTabIndex = index + 1;
            try { window.minimized = false; } catch (_) {}
        }
        window.index = 1;
        app.activate();
        return JSON.stringify({handled:true, reused:true});
    }
    // Fetch URL values in one Apple event. Reading each tab individually
    // grows the number of synchronous IPC calls with the browser's tab count.
    const windows = app.windows.tabs.url();
    for (let wi = 0; wi < windows.length; wi++) {
        const urls = windows[wi];
        for (let index = 0; index < urls.length; index++) {
            const candidate = urls[index];
            if (candidate === target) return focus(app.windows[wi], app.windows[wi].tabs[index], index);
            // Same Google document, even if its browser URL includes /edit or
            // account/query parameters. A boundary avoids matching ID prefixes.
            if (!documentMatch && docPrefix && typeof candidate === 'string' && candidate.startsWith(docPrefix)
                    && ['', '/', '?', '#'].includes(candidate.charAt(docPrefix.length)))
                documentMatch = {window:app.windows[wi], tab:app.windows[wi].tabs[index], index};
        }
    }
    if (documentMatch) return focus(documentMatch.window, documentMatch.tab, documentMatch.index);
    return JSON.stringify({handled:false, reused:false});
}
'''


def document_prefix(url: str) -> str:
    parsed = urlsplit(url)
    # Explicit document tabs, sheet ranges and anchors retain their destination.
    query = dict(parse_qsl(parsed.query))
    if parsed.hostname != 'docs.google.com' or parsed.fragment or {'tab', 'gid', 'range'} & query.keys():
        return ''
    match = re.match(r'^/(document|spreadsheets|presentation)/d/([A-Za-z0-9_-]+)(?:/|$)', parsed.path)
    return f'{parsed.scheme}://{parsed.netloc}{match[0].rstrip("/")}' if match else ''


class BrowserAutomationUnavailable(ValueError):
    """The native tab query failed; opening a fresh tab requires a user click."""


_automation_lock = threading.Lock()
_retry_after = 0.0
_failure_detail = ''
_RETRY_DELAY_S = 30


def focus_existing(url: str) -> bool:
    global _retry_after, _failure_detail
    # A nonresponding browser must not accumulate osascript processes from
    # double-clicks/concurrent clients, or cost another six seconds per click.
    with _automation_lock:
        if time.monotonic() < _retry_after:
            raise BrowserAutomationUnavailable(_failure_detail)
        try:
            result = subprocess.run(
                ['/usr/bin/osascript', '-l', 'JavaScript', '-e', SCRIPT, '--', url, document_prefix(url)],
                check=True, timeout=6, text=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            data = json.loads(result.stdout)
            if (not isinstance(data, dict) or type(data.get('handled')) is not bool
                    or type(data.get('reused')) is not bool or data['handled'] != data['reused']):
                raise ValueError('Invalid browser automation result')
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            if isinstance(exc, subprocess.TimeoutExpired) or '-1712' in str(getattr(exc, 'stderr', '')):
                detail = 'Your browser is not responding to macOS tab queries. Open the link below, or restart your browser before trying tab reuse again.'
            else:
                detail = "Could not reuse a browser tab. Allow Lab's process to control your browser in macOS Privacy & Security → Automation, or open the link below."
            _failure_detail = detail
            _retry_after = time.monotonic() + _RETRY_DELAY_S
            raise BrowserAutomationUnavailable(detail) from exc
        _retry_after = 0.0
        _failure_detail = ''
        return data['reused']
