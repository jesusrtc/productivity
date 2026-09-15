# Notebook modal centers the clicked area

Command-click carries the position within the clicked header, code, markdown,
or individual output into the cell modal. Center that location vertically in
the modal body and show a brief blue ripple there, alongside the cell outline.
Anchor within the area rather than the whole cell so revealing hidden code
does not displace a click in the results. Briefly follow image/chart resizing,
but stop recentering as soon as the user starts navigating. Regular Expand
button clicks still open at the cell header.
