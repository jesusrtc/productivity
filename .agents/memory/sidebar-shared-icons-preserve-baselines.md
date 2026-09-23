# Shared sidebar graphics preserve inline layout

Markdown file icons and GitHub history icons use shared CSS SVG graphics to
reduce per-row DOM and parsing. The Markdown inline-flex wrapper needs a 14px
empty `::before` item to keep the former inline SVG baseline; the symlink marker
uses `::after` independently. GitHub uses a currentColor mask to retain hover and
theme colors. Preserve icon dimensions and check text baselines and link overlays
when replacing any more inline graphics. Mixed and 5,000-file trees still exceed
the 200ms budget; the Markdown-heavy passing fixture is not general proof.
