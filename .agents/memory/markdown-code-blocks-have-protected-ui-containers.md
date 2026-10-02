# Markdown code blocks have protected UI containers

The user wants typing the third backtick on an empty line to autocomplete a
fenced Markdown block. Default language is None, with a visible language
dropdown and editable syntax highlighting for SQL, Python, and other supported
languages. Markdown remains the stored source. Keyboard deletion can clear
the body but must preserve its container; the block's Delete button removes it
and native Undo restores it. Protect literal fence lines typed or pasted into
the body by lengthening the outer delimiters. Keep imported empty blocks usable
and let arrows move out to surrounding paragraphs. Code controls are excluded
from rich copying.
