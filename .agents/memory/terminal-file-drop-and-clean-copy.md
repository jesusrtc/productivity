# Terminal file drops and clean copy

File rows across Lab's sidebars and repository trees are draggable. Carry the
row's absolute root/path identity into the active xterm, quote shell-sensitive
filenames, and use xterm.paste so bracketed-paste mode is respected. Never submit
the input. Do not interfere with existing terminal/tab reorder and linking drags.

Capture terminal copy events before xterm's handler to remove decorative box
rails while retaining content pipes, indentation, and Markdown tables. Empty
selections leave browser copy alone.

Chrome OS file drops generally expose only a basename, not the original absolute
path. Accept explicit local file URLs/path data; otherwise explain that the user
can drag from Lab or paste Finder's copied pathname. Never guess paths or silently
upload a copy as a substitute for the original file.
