# Editor keys are separate from IME setup

On Chrome 153, a plain textarea containing the 1,500-section fixture took a
median ~159 ms for a short multiline CDP `Input.insertText` append. A native
single key in the same control acknowledged in ~3.2 ms, with a ~17 ms browser
paint opportunity. CSS `contain:content` did not improve either path. This
does not identify all of the native IME cost or measure clipboard paste.

Use `lab_navigation_latency.py --document-edit --document-typing` to measure
native letters, digits, spaces, Enter and the production Tab handler, separately
from IME setup. Keys arrive every 25 ms without waiting for acknowledgments.
Verify trusted input, current clock mapping, exact value/cursor/focus at the edit
and paint opportunity, then exact persisted Save/Cancel contents in all four
fixture files. Keep the 200 ms editor/click/API gates and the separate IME
failure gate; successful native keys do not erase IME or navigation misses.
The first large run passed 1,122 keys (max 47 ms) but failed one 200.8 ms
workspace restore and one 236.4 ms IME setup.

This is browser input-to-paint-opportunity evidence, not physical display,
clipboard, composition-language or iTerm parity. No production editor change
was made from the control experiment.
