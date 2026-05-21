---
name: code-runner-darwin
description: >-
  Run Python code that lives in `content/code/` on the user's Darwin pod via
  the lab server's notebook executor (`POST /api/nb/exec`). Use when the user
  asks to execute, call, or test one of the existing functions under
  `content/code/` — e.g., "run greet from hello.py", "call fetch_recent for
  memberId 123", "use my code/ module to ...". Teaches the import convention
  (`from code.<X> import <Y>`, no preamble), where modules map on the pod,
  and how cells become live notebook entries in the UI. Do NOT use to *write*
  new modules — that is `code-skill-creator`'s job; this skill only *calls*
  existing modules.
---

# code-runner-darwin

A thin convention layer over `POST /api/nb/exec`. The mechanism is fully
automatic; this skill just teaches you the rules so you can compose
correct call cells.

## How it works

1. Modules live in `content/code/`. The folder is a Python package
   (`__init__.py` at the root). Sub-packages are allowed.
2. The lab server uploads any new/modified `.py` file to
   `{user}/code/...` on the pod before each `/api/nb/exec` call. First
   call per Darwin session also installs `lipy-davi` and prepends
   `~/code` to `sys.path`.
3. Modules that were just re-uploaded are auto-reloaded in the kernel
   (`importlib.reload`) so the cell sees fresh code without a kernel
   restart.
4. Cells therefore import as `from code.<module> import <symbol>` with
   **no preamble** — no `sys.path.insert`, no `pip install`.

## How to invoke a function

Pick a notebook path under any project (or `content/notebooks/` for
ad-hoc), then `POST /api/nb/exec` with a two-line cell:

```bash
curl -s -X POST http://localhost:3333/api/nb/exec \
  -H 'Content-Type: application/json' \
  -d '{
    "path": "content/projects/<id>/notebooks/<name>.ipynb",
    "code": "from code.<module> import <fn>\n<fn>(...)"
  }'
```

Same kernel session is pinned to the notebook path, so consecutive
cells share state.

## What's available

Check `content/code/` for the current set of modules. Each `.py` file
is importable as `code.<filename>`. Nested packages follow Python's
normal dotted convention: `content/code/sub/util.py` →
`from code.sub.util import ...`.

The hello-world smoke test exists at `content/code/hello.py` and
exposes `greet()` — useful as a sanity check that the loop is intact.

## When the call fails

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'code.X'` | File was created locally but server hasn't picked it up (file watcher / mtime drift) | Touch the file (`touch content/code/X.py`) and re-run. |
| `ModuleNotFoundError: No module named 'davi'` | `lipy-davi` install failed during bootstrap. | Re-run the cell — bootstrap retries. If it keeps failing, install manually via `darwin pod shell "pip install lipy-davi"`. |
| Cell still shows old behavior after editing | Reload of a sub-package only reloads the changed file; importing reload-resistant state (top-level constants captured by closures) needs a kernel restart | `POST /api/nb/session/restart` with the same path. |
| `darwin file upload failed for {user}/code/...` | Auth, pod cold-start, or a path that doesn't start with `{user}/` | Check `darwin pod status`. Set `DARWIN_USERNAME` env var on the server if the local USER differs from the LDAP id. |

## Heads-up

`code` shadows a stdlib module (interactive-interpreter helpers). Nothing
in the typical Trino/Spark workflow imports it, but if a future module
under `content/code/` ever does `import code` expecting the stdlib, it
will resolve to the package instead.
