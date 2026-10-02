# Inline code uses Slack-style highlighting

The user wants backtick inline code to resemble Slack: orange monospace text,
a filled background, a thin outline, and rounded corners. Keep this consistent
in the live Markdown editor and rendered documents/notebooks, with a darker
orange on a pale fill in light mode. Scope the shared rule to inline code so
fenced code keeps its syntax highlighting. The palette lives in the theme's
inline-code CSS variables in lab-shell.css.
