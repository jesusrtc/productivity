# Notebook click markers follow the text and use green

Use a green marker and green cell outline for Command-click navigation.
Capture the actual character plus the click's position inside its glyph, then
resolve that character in the modal after wrapping changes. Editable code uses
its highlighted text mirror for hit-testing. Percentages of a whole text block
drift when modal width changes; reserve that fallback for non-text clicks.
This refines `notebook-modal-centers-clicked-area.md`.
