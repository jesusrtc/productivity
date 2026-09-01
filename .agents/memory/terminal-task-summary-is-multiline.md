# Terminal context uses bounded scrollable request history

Show active agent context in a dedicated block between the compact
connection-status row and the terminal. Prefer one current `Objective` when a
provider exposes a genuine AI recap; otherwise show direct user requests since
`/clear` in chronological order under `Requests`.

Clamp each objective or request preview to two visual lines (backend cleanup
also caps an item at 280 characters). Both lists retain the complete history
and open at the newest request. Bound the header viewport to three two-line
items and the hover viewport to five; older requests remain scrollable.
