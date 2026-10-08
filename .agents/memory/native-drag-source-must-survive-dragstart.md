# Native drag sources must survive dragstart

Hiding a source or its modal synchronously in `dragstart` cancels Chrome's
native drag before it captures the payload. When a reader must close to expose
the terminal drop target, defer that close with `setTimeout(..., 0)`. Verify
this with real mouse dragging and Chrome's intercepted drag data; synthetic
`DragEvent` tests alone pass even when the native interaction is cancelled.
The sidebar drawer regression covers both Lab context sources and console
drops without Enter.
