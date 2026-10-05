# Terminal console layers stay below tabs

The expanded terminal switcher owns clicks across its complete visible area,
including where tab names, its scrollbar and width divider cover the console.
These clicks pin the list and must never dismiss it as terminal input.

Keep `.term-console` isolated as a stacking context. xterm helpers and top
decorations use z-index 5–7; without isolation they can sit above the sibling
switcher (z-index 2), so a transparent terminal layer steals tab clicks. The
native drawer regression includes an interactive xterm top layer and verifies
hit testing, tab selection, scrollbar/divider clicks and exposed-console input.
