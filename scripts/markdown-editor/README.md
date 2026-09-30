# Live Markdown editor bundle

The editor source is `core/src/core/static/js/lib/live-markdown-editor.js`.
It uses CodeMirror's plain Markdown document, native editing/undo, and block
decorations to render inactive content through Lab's shared sanitizer.

Rebuild the checked-in bundle and dependency licenses with:

```sh
cd scripts/markdown-editor
npm ci
npm run build
```

The shell loads the bundle only when an editable Assistant document opens.
No npm installation or external CDN is required to run Lab.
