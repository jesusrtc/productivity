# URL assets copy and open in Chrome

The user wants **Copy URL** and **Open in Chrome** in URL asset context menus,
including task assets and individual sublinks. Copy the exact saved destination,
including query parameters and fragments; keep assignments and drafts intact.
Chrome opening explicitly selects Google Chrome for local owner sessions, while
remote sessions use their own Chrome tab or explain the browser requirement.
Normal clicks retain pop-outs and Cmd/Ctrl-click retains browser tabs.
Both menu actions must remain discoverable through `lab ui`; the shared
`/api/ui/open-external` API accepts `browser: "chrome"`.
