# Shared file icons retain inherited colors

Every file icon now has one fixed-size span. Fixed-color glyphs reuse CSS SVG
backgrounds; image and generic document glyphs use currentColor masks so inherited
theme and Git colors remain live. Configuration files use `ft-json ft-conf`,
separate from JSON/lock `ft-braces`. Their stroke layer and theme-colored discs
preserve `--bg-primary`, including custom workspace colors. Symlink arrows retain
their independent `::after` overlay and the existing 13px/14px baselines.

The original inline vectors live in `core/tests/fixtures/file-icons-legacy.js`
for browser comparisons. Native-scale pixel checks permit only small mask/edge
compositing differences; 125% zoom checks geometry and saves screenshots because
CSS backgrounds and inline SVG rasterize differently at fractional sizes.

This brings 5,000-file SVG/config-heavy fixtures to 45,423 elements, allowing
pristine template/fragment reuse within the unchanged four-scope/60,000-element
bound. It reduces loaded typing delays but does not resolve startup typing,
every loaded input miss, or occasional workspace-files request delays.
