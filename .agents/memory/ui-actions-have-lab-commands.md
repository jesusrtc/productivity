# UI actions have Lab commands

The user wants agents to manipulate Lab in the same ways available in the UI,
including opening workspaces and renaming tabs. Every persistent UI operation
must have a Lab command path, and browser-only interaction must be callable.

Use `lab api routes`, `describe` and `call` for the shared public HTTP handlers,
schemas, validation and revision checks. Use `lab ui clients` and `inspect`,
then the visible controls or named UI commands for navigation, editing, layout,
menus and drag/drop. Select a specific client when several Lab views are open.
`lab context cli` contains the action map and browser-native limitations.

New features must remain discoverable through these command paths and include
CLI/UI verification. This expands features-need-lab-cli-access.md from managed
metadata operations to navigation and other UI interactions as well.
