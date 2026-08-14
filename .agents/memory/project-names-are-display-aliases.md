# Project names are display aliases

Project directory names and `project.json.id` are stable technical identifiers.
They continue to drive URLs, terminal ownership, config lookup, and API calls.

`project.json.name` is the editable human-facing label. The UI exposes it as
`display_name` while keeping the existing `name` field in project-list API rows
equal to the stable id for backward compatibility. Project rename controls must
write through `lab project set <id> name <value>` and must target the owning
workspace without changing the globally active workspace.
