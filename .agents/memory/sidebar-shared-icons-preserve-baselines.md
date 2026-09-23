# Shared sidebar graphics preserve inline layout

Markdown, Python, and SQL file icons and GitHub history icons use shared CSS SVG
graphics to reduce per-row DOM and parsing. The shared file-icon wrapper needs a 14px
empty `::before` item to keep the former inline SVG baseline; the symlink marker
uses `::after` independently. GitHub uses a currentColor mask to retain hover and
theme colors. Preserve icon dimensions and check text baselines and link overlays
when replacing any more inline graphics. Passing measured fixtures do not prove
all cold starts or unbounded tree sizes meet the 200ms budget.
