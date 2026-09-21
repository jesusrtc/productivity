# Document terminals release idle resources

The client wants an agent terminal associated with each opened document without
accumulating processes. Defaults: sleep after 60 idle minutes, expire the managed
association after 36 idle hours, and admit at most 3 running document terminals.
Policy and default agent are Lab-wide in the central settings view. Legacy
Assistant config remains a fallback until a global choice is saved. All embedded tabs share the root document's stable
identity. Opening alone never sends an agent task or modifies content.

Sleep kills the managed tmux/agent process and retains the exact provider thread
ID for resume. Active work, approvals and unknown activity states are protected.
The cap rejects new starts if no safely idle slot can be reclaimed. Expiry deletes
runtime context/association, not document content or provider chat history.

Keep one visible xterm/WS, disposing it on close/switch/hidden-page transitions.
Never touch the normal terminal cache or manually opened processes. The byte path
only updates RAM timestamps; cleanup runs in a low-frequency background worker.
