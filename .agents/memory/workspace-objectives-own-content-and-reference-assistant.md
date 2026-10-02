# Workspace objectives own content and reference Assistant

The user authorized the real workspace Objectives implementation after trying
the Home demo. It is opt-in per workspace: first creation enables the new
sidebar; the Home Objectives demo remains an independent browser sandbox.
The registry is `.lab/objectives.json`, owned Markdown/notebooks live under
`objectives/<id>/`, and Assistant documents stay original ID/location references.
Never migrate or repurpose Assistant tasks/content/terminal ownership to add
an objective. Terminal resource mappings are independent of fixed launch folders.
Use `lab objective` or the authenticated API for registry mutations.

See `docs/OBJECTIVES.md` for the storage and UI contract.
