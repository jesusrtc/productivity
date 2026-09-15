# Assistant document + creates a tab at the main level

The user wants the + in Document tabs to create a sibling of the first/main
content tab. It must not be indented under that first tab or under the selected
subtab. Add subtab in a row's menu still creates a nested child of that row.

Keep all these tabs inside the same task/note Markdown. top_level true marks
root-level tab placement; its typed parent still links to the document root for
membership/progress. Only direct root children can use this flag. Existing tabs
are not moved. Render that placement in both the rail and the generated Index.
