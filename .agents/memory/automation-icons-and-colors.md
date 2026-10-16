# Automation icons and colors

On October 16, 2026 the user requested automation-owned icons, with a command
window outline or any other icon, and a named/color-highlighted main like their
GitHub example. Main text and monochrome icons default to green. Children default
to white text in dark mode and inherit their main’s icon; allow explicit icon
and text-color overrides on each terminal. Keep custom task colors separate.

Use workspace Settings → Terminal automations → Icon and text color, including
built-in service icons, emoji and small PNG uploads. Show previews. The first
defined terminal is the standalone main; an existing parent keeps its name.
Persist appearance with saved sessions and recovery history. Default inheritance
follows the current parent, while explicit child overrides remain independent.
An appearance change never changes task ownership, linked assets or commands.

This supersedes older automation-white-name and generic-child-icon defaults for
new configured launches. Legacy running tabs without appearance metadata retain
their existing task/default icons. Support the same settings through `lab api`.
