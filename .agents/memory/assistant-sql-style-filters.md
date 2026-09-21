# SQL-style dashboard filters

The client prefers SQL-like conditions to nested JSON filter trees. Keep one
valid JSON per section, with schema 3 and a `where` string. Other settings
(title, position, sort, limit, id) remain in that JSON. Show filter stays the
only section header action; do not introduce another form or full SQL editor.

Example: `source = 'open' AND (is_RFC = true OR due <= TODAY + 2)`.
The server's bounded parser accepts AND/OR/NOT, parentheses, comparisons, IN,
BETWEEN, LIKE, CONTAINS, IS NULL and IS MISSING. No SQL/code execution. Bare
custom names check root attributes; attributes.name handles name collisions;
any_tab.name includes subtabs. Types and case are preserved. Priority and due
continue to match pending work; BETWEEN must use both bounds on one task.

Schema-1 and schema-2 settings remain readable and migrate with byte-preserving
backups, unchanged grouping/order and client-chosen P0 filters. Compiled ASTs
are generated API data, never stored alongside the authoritative where string.
