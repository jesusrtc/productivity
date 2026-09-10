# Terminal tab labels follow the rail width

The vertical terminal rail has a draggable, keyboard-accessible separator between
the tabs and console. Its browser-local width (`labTermSessionWidth`) ranges from
62 to 220 pixels, constrained to leave room for the console. Labels appear from
112 pixels and agent badges from 180 pixels. Resizing the outer panel temporarily
clamps the rail without losing its preferred width. Horizontal tabs adapt to the
panel width. The manual icons/text selector was removed at the user's request;
keep appearance automatic.
