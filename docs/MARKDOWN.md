# Rich Markdown and collapsible content

Lab Markdown supports ordinary Markdown plus safe HTML, including native
`<details>` / `<summary>` disclosures. Click the summary or focus it and press
Enter or Space to expand a block. Use this for generation prompts, source code,
supporting tables, or extra explanation beneath a chart.

````markdown
![Revenue chart](./revenue.png)

<details>
<summary>Query</summary>

Create a bar chart comparing monthly revenue across regions.

</details>

<details>
<summary>Python code</summary>

```python
df.groupby("region")["revenue"].sum().plot.bar()
```

</details>

<details open>
<summary>Source data</summary>

| Region | Revenue |
| --- | ---: |
| North | 120 |
| South | 90 |

</details>
````

Keep blank lines between the HTML tags and the Markdown content. Omit `open`
for a block that starts collapsed; include `open` to start expanded. Blocks
can be nested. A plain `> Query` is still a Markdown blockquote, not a fold.
Code is displayed, not executed. Use a notebook to execute Python.

## Editing documents

Select text to use the formatting toolbar, or use Cmd/Ctrl+B for bold,
Cmd/Ctrl+I for italic, and Cmd/Ctrl+E for inline code. A fully formatted
selection toggles that format off. A mixed selection combines its individual
runs into one formatted span; a second click removes the format. Formatting
outside the selection and other inline styles are preserved.

Type `/` on an empty line to open the block command menu. Type to filter,
use the arrow keys and Enter to choose, or click an action. Escape dismisses
the menu. **Foldable content** (also found with `/fold` or `/toggle`) inserts
a collapsed disclosure with its title selected for editing. The menu also
offers headings, lists, checkboxes, quotes, fenced code, tables, and dividers.
Each action can be undone in one step.

Type three backticks on an empty line to create a code block immediately.
The language starts as **None**; use its dropdown to select SQL, Python, or
another language and see syntax highlighting while editing. Fences stay
hidden and protected. Backspace or Delete can clear the code, while the
block's **Delete** button removes its container. Undo restores it. The arrow
keys at the first or last code line let you move to the surrounding document.
Code blocks are saved as ordinary Markdown fences with the selected language.

Tables keep their pipe-delimited Markdown source while displaying aligned,
wrapping cells with a distinct header. Empty cells remain editable. A table
still renders when its separator row has fewer or more columns than its
header; Lab does not rewrite the file to repair that mismatch.

## Copying to Google Docs

The document Copy button, section Copy buttons, and Assistant copy actions
snapshot the rendered document when you click:

- Collapsed blocks are omitted entirely, including their summary labels.
- Expanded blocks become ordinary content, with their summary as a bold label.
- Closed blocks inside open blocks are also omitted. An open child inside a
  closed parent stays excluded.
- Images outside collapsed blocks are included; hidden images are not fetched
  for copying. Tables and code retain rich formatting.
- The plain-text clipboard representation and fallback use the same filtered
  content. Assistant plain-text actions copy readable expanded text.

Expanding a block controls whether it appears in the next copy. Copying does
not edit the Markdown file, change its default state, or change the page theme.

## HTML support

The main Lab file, notebook Markdown, and Assistant renderers sanitize HTML
using locally vendored DOMPurify. Document formatting, links, images, tables,
and disclosure blocks are supported. Scripts, event handlers, frames, forms,
and embedded CSS are excluded from Markdown. Standalone HTML files remain the
appropriate place for custom interactive pages.
