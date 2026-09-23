# A terminated echo footer may fill the cursor cell at the right margin

Tmux can leave its cursor on the last occupied cell when output fills a row.
For the scrolling-output probe, that cell may contain the required footer `|`.
Reading only up to the cursor excludes the terminator and waits for another key,
overcounting latency by up to a key interval. Native 49-column runs confirmed
this at input lengths 2 and 51 with cursorX=48 in both parse and render callbacks.

Include that last cell only for the explicitly terminated footer protocol; exact
input, no-ahead checks, independent prefix continuity and actual cursor-row render
coverage remain necessary. An incomplete terminator must still wait. Preserve
the ordinary echo path, which has no terminator to disambiguate that cell, and
retain earlier measurements with their conservative boundary limitation noted.
