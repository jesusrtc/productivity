# Explicitly refresh Lab managed agent instructions

The user replaced automatic seeding on new workflow/Objective creation with an
explicit refresh action. The top-bar update/restart button captures the current
vault, workspace and selected Objective, then refreshes their AGENTS.md files
using the new installed template after restart. `lab agents refresh` exposes the
same scoped writer without pulling or restarting.

Create missing files; place one marked Lab managed section first with the brief
instruction to run `lab context llm`, read the full output and follow it before
working. Replace only complete managed sections, deduplicate/move them to the
top, preserve all other bytes and avoid rewriting current files. Preserve and
report symlinks or malformed markers. Do not scan unrelated scopes/checkouts.
This explicitly authorized section is the narrow exception to the earlier
no-instruction-generation policy; legacy sync, context reads and ordinary
creation remain nonmutating. Do not create skill links or memory policies.
