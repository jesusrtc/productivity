# Lab context is available and draggable

The user wants Lab agent context in every workspace, including the modern
Objective/project Files sidebar. Reuse the installed launch guide reader at
`/api/agents/context/guide`; do not generate instruction files in workspaces.
The sidebar shortcut and its read-only viewer offer a drag action that pastes
the full guide into the attached terminal without Enter. Capture the target
session/socket/workspace before fetching, and cancel a late paste after a
selection change. Preserve multiline content for bracketed-paste agents and
flatten it to one unsent line for plain shells.
