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
