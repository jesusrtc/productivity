# Terminal copy rejoins wrapped prose

Terminal copy removes decorative rails and trailing screen padding, then
rejoins application-wrapped prose and split identifier fragments. Preserve
blank paragraphs, separate list items, indentation, code fences, commands,
SQL, and meaningful pipes/table rows. Xterm already joins native soft wraps;
the extra handling is for application-rendered hard wraps inside the pane.
Do not flatten every newline or append identifier-adjacent prose to a name.

`node scripts/check-terminal-copy.mjs` checks the real Lab copy listener and
Chrome clipboard using a browser-only terminal in an isolated profile. It
tests the user's examples at narrow and wide terminal sizes, partial/mouse
selections, and the platform copy shortcut. Never read pre-existing clipboard
contents in this test: write test-owned content before any clipboard read.
