# Shared sidebar graphics preserve inline layout

Markdown, Python, SQL, and JSON/lock icons use shared CSS SVG graphics to reduce
per-row DOM and parsing. JSON/lock uses `ft-braces`; configuration files retain
their different glyph despite also using `ft-json`.

The 16px file-icon wrapper is now `inline-block`, with centered remaining inline
SVGs positioned absolutely. Preserve the former flex baseline using vertical
alignment -4px for 14px glyphs, -4.5px for the 13px image/PDF/generic glyphs. The
former empty baseline `::before` is no longer needed; the symlink marker still
uses `::after`. Chrome tests compare 19 icon families in inline/flex contexts,
with/without symlinks, both themes, and 100/125% zoom.

Recent-file history buttons themselves carry `sidebar-actions`, eliminating the
wrapper. Preserve the legacy grouped-button selectors, direct-button hover/theme
styling, opacity, keyboard activation, and Git badge placement before the action.
GitHub keeps its currentColor mask. Shared graphics and simpler layout reduced
the mixed-file fixture to 45,423 elements but did not solve all typing misses;
SVG-heavy lists still exceed the unchanged 60,000-element template cache bound.
