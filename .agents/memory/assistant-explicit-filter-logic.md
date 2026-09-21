# Dashboard filters have explicit AND/OR groups

The client requested human-readable valid JSON with explicit logical operators.
Schema-2 section JSON uses `filter` with nested `and` / `or` arrays and one
condition per leaf. Omit inactive/blank filters; no implicit `match: any` rules.
The editor expands logical groups while keeping short conditions on one line.

Migrate schema-1 flat settings by preserving their exact grouping: source and
other filters are ANDed with the priority/deadline group, whose previous match
value selects OR or AND. Preserve P0 selections, section positions and custom
filters; retain original section bytes in a backup before writing schema 2.
