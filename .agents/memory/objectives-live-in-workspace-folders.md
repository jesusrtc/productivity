# Objectives live in workspace folders

The user requires Objective content to be owned by each workspace/Objective
folder, rather than centralized in framework metadata. Discover
`objectives/<folder>/.objective.json` directly; its stable ID is independent of
the folder name. Links, tasks, resources, worktrees and asset associations live
in that manifest. Owned Markdown/notebook paths are relative to its folder.
Assistant and existing-file references retain original ownership.

Only focus/order IDs and terminal UI mappings belong in
`.lab/objectives-state.json`. Legacy `.lab/objectives.json` is read-compatible;
`lab objective migrate --workspace <id> [--apply]` previews/converts it with a
byte-identical backup. Reads never migrate; valid Objective mutations convert
that workspace. Preserve IDs, unknown fields, documents and exact subtabs.
See `lab migrations workspace-objectives` and `docs/OBJECTIVES.md`.

This supersedes the storage location in
`workspace-objectives-own-content-and-reference-assistant.md`.
