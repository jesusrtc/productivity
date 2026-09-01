# Terminal task summary gets its own multiline block

Show the active agent's latest three direct requests in a dedicated `Requests`
block between the compact connection-status row and the terminal. Keep them in
chronological order, preserve newlines between them, and clamp the total block
at six lines; do not squeeze request context into the one-line connection strip.
