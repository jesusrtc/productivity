# tmux creation hooks must preserve API errors

`tmux new-session` can create its pane and still return nonzero because a
user's `after-new-session` hook fails. Lab currently returns HTTP 500 and skips
wheel configuration and success metadata in this case. Preserve that behavior.

A rejected one-client optimization appended wheel setup to new-session.
Neither `new-session -P -F <marker>` nor a following `display-message -p
<marker>` distinguished hook errors from later best-effort wheel errors:
both markers appeared despite the hook failure. Treating a marker as creation
success incorrectly returned HTTP 200. Keep creation and configuration separate
unless a replacement proves this distinction against real tmux.

`core/tests/test_term_creation_native.py` covers the real API on a private
`TMUX_TMPDIR` server, including hook errors, unchanged settings after failure,
shell argv/cwd, named socket routing, saved identity and repeat-create adoption.
The test kills and checks only its owned private server and pane processes.
