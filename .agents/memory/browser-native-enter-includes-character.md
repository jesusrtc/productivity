# Native Enter tests include the character event

In Chrome CDP keyboard tests, use `Input.dispatchKeyEvent` with `type: 'keyDown'`,
`key/code: 'Enter'`, `windowsVirtualKeyCode: 13`, and `text/unmodifiedText: '\r'`,
followed by keyUp. On the installed Chrome 153, a keyDown without text did not
activate the focused native button; the complete keystroke did.
Validate the resulting action count and focus instead of treating a raw keyDown
as proof that the native Enter activation path was exercised.
