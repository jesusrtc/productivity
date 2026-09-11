# Markdown in Lab

Use normal Markdown plus safe HTML disclosures for supporting material.
The main Lab Markdown and Assistant views support this syntax:

````markdown
![Chart](./chart.png)

<details>
<summary>Query</summary>

Describe the prompt that produced the chart here.

</details>

<details>
<summary>Python code</summary>

```python
print("hello")
```

</details>

<details open>
<summary>Source data</summary>

| Item | Value |
| --- | ---: |
| Example | 42 |

</details>
````

Disclosures support fenced code such as `sql`, `python`, or an unlabeled fence,
including immediately after `</summary>` without a blank line. Each code block
has a **Copy** button at the upper right that copies only its code, preserving
indentation and line breaks. Add `open` only when the block should start
expanded. Blocks may be nested. `> Query` is an ordinary blockquote, not a
disclosure. Code is displayed, not executed.

Google Docs copy snapshots the current view: closed blocks and their labels
are omitted, open blocks become regular text with a bold summary label, and
closed children inside open parents remain omitted. This also applies to
section copy, Assistant copy actions, plain-text clipboard data, and fallback
copying. Copying does not change the source file or its default open state.

Lab sanitizes HTML in its main Markdown renderer. Scripts, event handlers,
frames, forms, and embedded CSS are excluded. Use a standalone HTML file for a
custom interactive page. Choose file names and content using the workspace's
own instructions and the user's request.
