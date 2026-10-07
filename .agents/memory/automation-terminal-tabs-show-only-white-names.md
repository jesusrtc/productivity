# Automation terminal tabs show only white names

The folded-rail behavior below is superseded by
[Automation terminals show white bullets when folded](automation-terminal-folded-white-bullets.md).

Automation-created tabs use just their saved display names in the primary text
color (white in the default dark theme), as in the user’s October 7 screenshot.
Omit task dots, terminal or asset icons, activity/completion badges, order numbers,
folder captions, recency decoration and visible child-carets on these rows. Keep
the name visible in compact rails, with the usual hover and selection highlight.

Recognize automation tabs by their existing stable logical names:
automation-<32 lowercase hexadecimal run UUID>-<positive step index>. This also
covers existing launches and restored sessions without a metadata migration.
Fixed main roles keep their special icons and ordinary tabs keep their styles.
Preserve hierarchy, hover/keyboard unfolding, drag/drop and task context. Retain
context/status details in accessible labels and hover metadata.
