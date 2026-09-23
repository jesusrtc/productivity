# Terminal creation waits for rendered output and identity

The native navigation runner's --terminal-create workflow uses ordinary
New/Terminal clicks with a configured owned echo shell. Count the first rendered
marker in the selected, focused, sole visible pane with an open socket; then
verify a native key and unique live/saved identities in the owning workspace.
Keep initial workspace/picker timings and the production pane bounds. This
isolates Lab creation and does not measure user shell scripts or agent startup.

Fixtures must be loopback-only disposable lab-navigation vaults, restore SHELL,
preserve foreign sessions, and verify the recorded producer PID/cwd before
owned-only cleanup. Use exact session-name listing after deletion: tmux
has-session accepts prefixes, so removed bash-2 can still match live bash-20.
All latency failures remain in reports, including runs with cleanup diagnostics.
