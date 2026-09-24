# Terminal process discovery is TTY-scoped

Codex metadata needs the PID-to-TTY mapping only for the terminal panes in
that request. Use `ps -t <comma-separated TTYs> -o pid=,tty=` with normalized
TTY names (including Linux `pts/N`), then retain the output membership check.
Do not restore `ps -axo`: on the September 2026 busy Mac baseline the full
process listing cost 185–196 ms by itself; two-TTY selection took 4.5–5 ms.
The targeted selection preserves exact PID mapping and `/new`/`/clear`
handling while keeping the existing metadata cache and connection cleanup.
