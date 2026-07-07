# Codex background processes need tmux

When verifying long-lived local services from Codex, a plain `nohup ... &`
started inside an `exec_command` may still be cleaned up when the tool command
returns. For persistent verification of `make start`, launch it from a detached
tmux session and then inspect the process/port separately.
