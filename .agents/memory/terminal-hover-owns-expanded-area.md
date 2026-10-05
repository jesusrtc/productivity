# Terminal hover owns the expanded area

Keep the terminal list expanded while the pointer is anywhere over its full
visible area, including its right edge and scrollbar. Its hover container must
have the expanded list's actual width; reserving only 62px for it in the terminal
layout is a separate concern. Returning focus to xterm after a tab click must
not collapse the list while the pointer is still over it.
