# Local Mac workspace browser opening reuses existing tabs

The user requested backend-managed Mac scripting and pointed to
`~/.alfred/Alfred.alfredpreferences/workflows/user.workflow.E4A2C27B-492C-42B4-BDB7-162D55FC71F8/info.plist`.
Its URL action searches Chrome windows, activates a matching tab, and opens a
new tab only if no match exists. Lab adapts this behavior in `core/browser_tabs.py`
without depending on that external Alfred installation.

Workspace browser actions request `reuse_existing:true` through
`/api/ui/open-external` when `LAB_NATIVE_BROWSER_REUSE` permits it. The backend
requires the local owner, loopback host, and same-origin request; macOS's default
browser is resolved through NSWorkspace. Chrome-family browsers and Safari use
JXA to focus an exact URL match without changing its URL or reloading it. Generic
Google document links can match the same document with different display/account
parameters; explicit tabs, ranges, and anchors retain exact destinations.
Unsupported browsers and absent matches use the normal OS opener.

Pass URLs as osascript argv data, never as executable script text. Bound the
automation call and surface failure with a fresh browser-click fallback; do not
silently duplicate a tab after a permission error or timeout. macOS may require
Automation access for the Lab launcher. Remote clients and modified clicks keep
client-side opening. Loopback alone cannot distinguish an SSH-forwarded client
from a local desktop: the native helper controls the Mac running the backend,
never a remote client's browser. This explicit native workspace action refines
the former unconditional client-only fallback policy.
