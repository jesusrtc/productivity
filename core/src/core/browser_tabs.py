"""Focus an existing default-browser tab on macOS without reloading it.

Adapted from the Chrome tab action in the user's Alfred URL workflow. URL
arguments are data, never interpolated into executable AppleScript/JXA.
"""
import json
import re
import subprocess
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
    for (const window of app.windows()) {
        const tabs = window.tabs();
        for (let index = 0; index < tabs.length; index++) {
            const candidate = tabs[index].url();
            if (candidate === target) return focus(window, tabs[index], index);
            // Same Google document, even if its browser URL includes /edit or
            // account/query parameters. A boundary avoids matching ID prefixes.
            if (!documentMatch && docPrefix && typeof candidate === 'string' && candidate.startsWith(docPrefix)
                    && ['', '/', '?', '#'].includes(candidate.charAt(docPrefix.length)))
                documentMatch = {window, tab:tabs[index], index};
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


def focus_existing(url: str) -> bool:
    result = subprocess.run(
        ['/usr/bin/osascript', '-l', 'JavaScript', '-e', SCRIPT, '--', url, document_prefix(url)],
        check=True, timeout=6, text=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or type(data.get('handled')) is not bool:
        raise ValueError('Invalid browser automation result')
    return data['handled']
