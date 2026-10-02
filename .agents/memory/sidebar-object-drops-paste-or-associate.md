# Sidebar object drops paste or associate by target

The user wants every object in the Objective sidebar to work with terminals:
documents, internal subtabs, notebooks, URLs, Tasks, files, folders, Root,
the Objective directory, and worktrees. Drop inside the console to paste a
shell-quoted reference without submitting input. Capture the source root/path
at drag start, preserve `#tab=<id>`, and do not substitute the active worktree.
Tasks references its common details document or its actual registry entry.

Drop on a terminal name to associate the object; dragging a terminal onto an
Objective resource, Tasks, or folder/worktree also associates it. Clicking that
terminal opens the object. Store folder and Tasks mappings independently in
the Objective registry, validate folder boundaries after symlink resolution,
and preserve launch folders, processes, labels, conversations and Assistant
ownership. The running terminal receives no input during association.

Ordinary workspace link rows and folder shortcuts also paste references.
See `docs/OBJECTIVES.md` and the native staging drag evidence.
