# Terminal context is scrollable and two lines per item

Show active agent context in a dedicated block between the compact
connection-status row and the terminal. Prefer one current `Objective` when a
provider exposes a genuine AI recap; otherwise show every direct user request
since `/clear` in chronological order under `Requests`.

The block and hover request list scroll vertically. Clamp each objective or
request preview to two visual lines (backend cleanup also caps an item at 280
characters), but do not cap the number of requests. Start at the newest item
and preserve the user's scroll position across unchanged polling refreshes.
