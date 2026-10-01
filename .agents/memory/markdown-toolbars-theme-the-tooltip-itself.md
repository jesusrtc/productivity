# Markdown toolbars theme the tooltip itself

CodeMirror puts `cm-tooltip` on the toolbar element itself, so a `:has()` rule
looking for a descendant toolbar does not theme it. Style both classes on the
same element, use fixed interface-size text, and verify contrast in both themes.
The user reported white labels disappearing on the default pale tooltip.
The native word-editor test verifies the theme background, label contrast,
fixed type size, and viewport bounds on desktop and narrow screens.
