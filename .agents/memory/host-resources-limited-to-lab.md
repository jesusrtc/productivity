# Host resource controls are limited to Lab work

The user requested host monitoring and stop controls, then explicitly narrowed
the targets to Lab, Jupyter and scanning activity. Keep unrelated host apps out
of the process list and controls. The top-bar Resources panel shows overall
host metrics but admits processes only through Lab server/tmux ancestry, with
PID plus creation-time revalidation before signals. Protect the server and
shared tmux transport. Files-view scans run inside the server, so pause them
cooperatively and prevent browser polls restarting them; preserve cached files.
See docs/RESOURCES.md for scope, polling and restart behavior.
