# Terminal WebSockets close when their PTY exits

A tmux attach process can exit while the browser is still connected. The old
handler returned from its output pump but left receive_text waiting forever,
so document terminals showed Ready above [exited].

The connection now waits for either its PTY output pump or keyboard input pump
to finish, then cancels both, releases the PTY, sends an exit frame and closes
the WebSocket. Keep this event-driven; do not depend on a keypress or a session
poll to discover EOF. Browser document terminals expose a reconnect action and
do not automatically relaunch agents that keep failing at startup.

Regression coverage: test_document_terminal_connection.py exercises real pipe
EOF with and without final error output and verifies cancellation/descriptor
release. test_frontend_document_terminal.py covers the browser exit frame.
Normal terminal auto-reconnect behavior remains owned by lab-app.js.
