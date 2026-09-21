# Client-defined attributes on documents and tabs

The client requested custom flags such as `is_investigation` or `is_RFC`, usable
in dashboard filters. Optional `attributes` metadata holds a client-defined JSON
object on tasks, notes, series and subtabs. No names or values are preassigned.
Each tab owns its attributes; edits preserve bodies, identity and sibling tabs.
The Attributes button edits the whole JSON object, with conflict checking.
CLI `set <id> attributes '<JSON>'` replaces the object; preserve other keys in
targeted changes. `{}` and null clear it.

Schema-2 section filters accept `{"attribute":{"name":"is_RFC","equals":true}}`
inside arbitrary AND/OR groups. Use exactly one of equals, contains or exists.
JSON types and case matter; absent, null, false and zero are distinct. Default
scope is document; any_tab checks the root plus all embedded subtabs. Grouped
series still show once, opening the latest note if an older member matched.

Implementation: assistant_attributes.py validates metadata; assistant_dashboard.py
validates filter leaves; assistant.js provides the JSON editor and matcher.
API and isolated Chrome tests cover typed values, missing keys, scope, content
preservation, conflicts and moves between custom dashboard sections.
