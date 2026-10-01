# Live Markdown editor bundle

The editor source is `core/src/core/static/js/lib/live-markdown-editor.js`.
It keeps CodeMirror's plain Markdown document and native editing/undo, with
document typography throughout the editable content. Formatting delimiters and
link destinations appear only for the inline span at the caret or selection.
Headings, lists, checkboxes, quotes, tables and code retain their formatting
while editing; complex previews use Lab's shared Markdown sanitizer.

Select text for the compact formatting toolbar, or use Cmd/Ctrl+B, I, and E for
bold, italic and inline code. Cmd/Ctrl+S saves the current tab. The owning
Assistant view retains idle autosave, drafts and independent tab bodies.

Rebuild the checked-in bundle and dependency licenses with:

```sh
cd scripts/markdown-editor
npm ci
npm run build
```

The shell loads the bundle only when an editable Assistant document opens.
No npm installation or external CDN is required to run Lab.

The lockfile must contain ordinary `node_modules/` package entries. Temporary
build-directory links break `npm ci` on another checkout.
