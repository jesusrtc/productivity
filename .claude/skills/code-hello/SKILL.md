---
name: code-hello
description: >-
  Run `greet()` from `content/code/hello.py` on the user's Darwin pod. Smoke
  test and canonical reference template for the `content/code/` code-runner
  system. Invoke when the user says "say hello on darwin", "run greet",
  "greet me", "greet <name>", "test the hello-world cell", "smoke-test the
  code runner", or "is the darwin code runner working".
---

# code-hello

A one-function module that proves the `content/code/` → Darwin loop
works. Useful when you (or a future agent) want to confirm the lab
server can still upload, import, and run a cell after some change.

## Function API

```python
# content/code/hello.py
def greet(name: str = "world") -> None:
    """Print 'hello {name} from hello.py' to stdout."""
```

- No return value (prints to stdout).
- `name` defaults to `"world"` if not passed.

Expected stdout:

```
hello world from hello.py
```

(or `hello jesus from hello.py` when called with `greet("jesus")`).

## Call snippets

```python
from code.hello import greet
greet()
greet("jesus")
```

## How to actually invoke a cell

The notebook-executor mechanics — `POST /api/nb/exec`, notebook path
conventions, kernel session pinning, file upload, troubleshooting —
live in **`code-runner-darwin`**. Use this skill for *what* to call;
use that one for *how* to call.

## When this fails

If `greet()` doesn't print on the cell, the problem is plumbing, not
this module. See `code-runner-darwin`'s troubleshooting table.
