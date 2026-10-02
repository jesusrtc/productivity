# Headless macOS select uses native type-to-select

Headless Chrome on macOS ignored CDP ArrowDown and Enter for both a plain HTML
select and the Markdown code-language select, with no preventDefault or editor
keymap involved. Native type-to-select works: focus the select and send a CDP
keyDown with the letter in both key and text, then keyUp. It produces real input
and change events. Do not replace dropdown integration checks with synthetic
change events or change product behavior to accommodate the platform popup.
