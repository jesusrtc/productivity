# Markdown preview clicks cannot dispatch from measurement callbacks

The original live Markdown bundle dispatched caret changes inside a
requestMeasure.write callback. CodeMirror forbids updates there, producing the
EditorView.update re-entry error. The current editor maps preview text positions
in the click handler instead. Native word-level editor regressions must capture
console errors, window errors and rejected promises as well as checking content;
otherwise CodeMirror may log an exception while an interaction test still passes.
