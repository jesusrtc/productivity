# Terminal request history survives clears

Click the Requests/Objective strip label to open the physical terminal's
request history. Use three-line expandable previews, full original submitted
text, and visible /clear, /new or detected conversation-refresh dividers.
Keep expanded rows and reading position during updates; native dialog Escape
and close restore focus. The modal stays scoped to the terminal it opened for.

Provider transcripts are authoritative for requests, including edited and
pasted multiline text. Never reconstruct prompts from raw PTY input: it also
contains drafts, shell commands and interactive menus. Enter schedules fresh
reads; a small conservative input tracker recognizes only explicit /clear or
/new submissions, and never stores its draft. Unknown cursor edits fall back
to provider events and detected thread changes.

core/terminal_requests.py retains full accepted text in the client-wide
$LAB_HOME/terminal-requests.sqlite3 keyed by physical terminal name, separate
from the compact 280-character current-thread metadata. Incremental transcript
reads keep incomplete writes for the next poll. Content plus occurrence keys
deduplicate provider projections while retaining identical repeated requests.
History endpoints reuse the scoped terminal list's access checks, including
borrowed document terminals; a terminal UUID alone is not authorization.
