# File context menu copies raw content

The shared file secondary-click menu includes **Copy content** in workspace,
vault, framework, and repository trees. Fetch the clicked file afresh using
its captured root and path, and copy the returned source text to the clipboard.
Markdown syntax and closed disclosure content stay intact; notebooks copy
their raw JSON. This action is separate from rendered-document rich copy.
Show success or failure feedback, and omit the action from folder menus.
