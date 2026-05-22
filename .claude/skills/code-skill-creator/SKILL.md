---
name: code-skill-creator
description: >-
  Create a new Python module under `content/code/` AND mint its matching
  per-capability skill at `.claude/skills/code-<module>/SKILL.md` (or
  `code-investigation-<module>/` for trust/safety modules), so the user can
  later invoke it via `from code.<module> import <fn>` through
  `POST /api/nb/exec`. Invoke when the user says "create a function that
  ...", "make me a code module that ...", "add a helper in content/code
  ...", "make a script that fetches/queries/checks ...", "I want a function
  I can call from Claude that ...", or "write some Darwin code that ...".
  Companion to `code-runner-darwin` — that one runs existing modules, this
  one writes new ones and hands off to a smoke-test cell to prove the new
  code works.
---

# code-skill-creator

The user describes a task they want runnable as a Python function on
Darwin. You produce: (1) the module file, (2) a smoke-test invocation,
and — only when needed — (3) a per-capability skill describing how to
invoke it.

## The flow

For every request, do these steps in order. Do **not** skip steps; do
**not** ask for confirmation between them unless the user's intent is
genuinely ambiguous.

### 1. Pick a module path

- **Single-file capability** → `content/code/<verb_or_noun>.py`
  (e.g., `registrations.py`, `pod_info.py`, `member_lookup.py`).
- **Multi-file capability** → `content/code/<area>/<file>.py` and add
  `content/code/<area>/__init__.py` (empty).
- File names use `snake_case`. Avoid names that shadow stdlib (`code`
  is already taken at the package level; don't add `email.py`,
  `json.py`, etc.).

### 2. Write the module

Start from this skeleton:

```python
"""<one-line description of what this module does>."""
from __future__ import annotations

# Imports go here. lipy-davi is installed automatically by the bootstrap;
# you can `from davi import ...` directly. Trino / Spark helpers go via
# davi.

def <fn_name>(<args with type hints>) -> <return type>:
    """<one-line description of what the function returns>.

    Args:
        <arg>: <one-line>
    """
    ...
```

Rules:
- **Type hints on everything.** Args and return.
- **No global side effects** at import time (no print, no network call).
  Side effects go inside functions.
- **Return data, don't just print** — printed output is fine for
  smoke-test demos, but real callers want values they can use.
- **Imports of lipy-davi / trino / spark are fine** — the bootstrap
  installs lipy-davi and prepends sys.path. Other deps require a
  `darwin pod shell "pip install <pkg>"` first; flag this to the user.

### 3. Save and smoke-test

Write the file via the Write tool. Then immediately exercise it through
`POST /api/nb/exec`:

```bash
curl -s -X POST "$(scripts/lab-url.sh)/api/nb/exec" \
  -H 'Content-Type: application/json' \
  -d '{
    "path": "content/projects/<project>/notebooks/<name>.ipynb",
    "code": "from code.<module> import <fn>\nresult = <fn>(<sample args>)\nprint(result)"
  }'
```

If the smoke test fails:
- `ModuleNotFoundError` → file path wrong, or `__init__.py` missing for
  sub-packages.
- `ImportError: No module named '<dep>'` → dep not installed on pod;
  recommend `darwin pod shell "pip install <dep>"` and retry.
- Logic errors → fix the code, re-run; the mtime-diff push + reload
  will pick up the edit automatically.

### 4. Always create a per-capability skill

**Every module in `content/code/` gets a matching skill at
`.claude/skills/<skill-name>/SKILL.md`.** No exceptions. This is what
makes the module discoverable via natural-language triggers — without
it, the user has to remember the function signature and call it through
the umbrella.

**Skill-name rule:**

- **Investigation-flavored modules** → `code-investigation-<module>`.
  This is the default. Anything that queries Trino/Spark for trust
  & safety signals (member lookups, restrictions, abuse cohorts,
  registration funnels, login analysis, scraping, ATO, payment
  fraud, telesign, JSS, etc.) is investigation-flavored.
- **General-purpose modules** → `code-<module>` (no prefix). Use this
  only for genuinely non-investigation utilities: smoke tests
  (`code-hello`), pod introspection (`code-pod_info`), formatting
  helpers, environment probes.

When unsure: look at what the function returns. If it returns
trust/safety data tied to members, accounts, or abuse signals, it's
investigation-flavored. Otherwise it's general-purpose.

The skill must include:

- **`name:`** — exactly the skill-name chosen by the rule above
  (kebab-case mirror of the module filename, with the
  `code-investigation-` or `code-` prefix).
- **`description:`** — what the module does, followed by a list of 4–8
  natural-language trigger phrases the user might say. Pull triggers
  from the function's actual behavior; don't invent generic ones.
- **Function API** — copy the function signature and docstring verbatim
  so the skill body stays in sync with the real code. Note args, return
  type, and any side effects (stdout, file writes, etc.).
- **Expected output** — what the function returns or prints on a
  successful run, so future-you can spot regressions at a glance.
- **Call snippets** — short Python snippets showing the import + call
  (`from code.<module> import <fn>` then `<fn>(...)`). Include both
  default-arg and custom-arg shapes if both are useful. **Do NOT
  include a curl recipe or `/api/nb/exec` payload here** — those
  mechanics already live in `code-runner-darwin`. Per-capability skills
  document *what* the function does (its API); the runner skill
  documents *how* to invoke it. Duplicating the curl across every
  per-capability skill creates drift.
- **Pointer to `code-runner-darwin`** — one line directing the reader
  there for invocation mechanics.
- **When this fails** — one or two sentences. For plumbing issues
  point to `code-runner-darwin`; here only mention module-specific
  failure modes (bad arguments, missing data, etc.).

Use `.claude/skills/code-hello/SKILL.md` as the canonical template. New
skills should be structurally identical — same section headings (Function
API → Call snippets → How to actually invoke a cell → When this fails),
same order — so a reader who's seen one can navigate any of them.

### 5. Tell the user what you did

End with a one-paragraph summary:
- File created (path).
- Smoke-test output (the actual printed/returned value).
- Per-capability skill created at `.claude/skills/code-<module>/SKILL.md`.

## What you don't do

- **Do not** edit `content/code/__init__.py`. It stays empty. Top-level
  helpers go in their own file, not re-exported from the package root.
- **Do not** skip the per-capability skill. Every module gets one — that's the policy.
- **Do not** invent dependencies. If a function needs `pandas`, check
  if it's already on the pod (`darwin pod shell "python -c 'import
  pandas'"`); if not, flag the install to the user before writing code
  that assumes it.
- **Do not** push files manually with `darwin file upload` or `darwin
  pod shell` — that happens automatically via the lab server when you
  call `/api/nb/exec`. Just write the file locally.

## Example transcripts

### Example A — general-purpose

> User: "make a function that returns the current pod hostname"

1. Module path: `content/code/pod_info.py` (single-file, generic).
   Skill flavor: **general-purpose** (introspection, not trust/safety
   data). Skill name will be `code-pod_info`, no prefix.
2. Write the file:
   ```python
   """Helpers for inspecting the Darwin pod environment."""
   from __future__ import annotations
   import socket


   def hostname() -> str:
       """Return the pod's hostname as reported by the kernel."""
       return socket.gethostname()
   ```
3. Smoke test:
   ```bash
   curl -s -X POST "$(scripts/lab-url.sh)/api/nb/exec" -H 'Content-Type: application/json' \
     -d '{"path":"content/projects/code-runner-demo/notebooks/pod_info.ipynb",
          "code":"from code.pod_info import hostname\nprint(hostname())"}'
   ```
   → `jupyter-jcortes-...` (or similar).
4. Per-capability skill at `.claude/skills/code-pod_info/SKILL.md` —
   triggers: "what's the pod hostname", "show me the pod name",
   "which pod am I on", "pod identity", "darwin pod hostname".
   Mirrors the `code-hello` skill structure (Function API + Call
   snippets + pointer to `code-runner-darwin` + failure pointer).
   No curl here — that lives in `code-runner-darwin`.
5. Reply: "Wrote `content/code/pod_info.py` with `hostname()`. Smoke
   test prints `jupyter-jcortes-...`. Per-capability skill
   `code-pod_info` created."

### Example B — investigation-flavored

> User: "make a function that fetches the last N registration events for a memberId"

1. Module path: `content/code/registrations.py` (single-file).
   Skill flavor: **investigation** (returns trust/safety data tied
   to a member). Skill name will be `code-investigation-registrations`.
2. Write the file (uses `davi`/Trino for the lookup; type hints on
   args and return; no module-level side effects).
3. Smoke test against a known good memberId, confirm the row count
   and shape look right.
4. Per-capability skill at
   `.claude/skills/code-investigation-registrations/SKILL.md` —
   triggers: "show me recent registrations for member X", "what are
   the last N registration events for memberId Y", "registration
   history for member Z", "pull registration events for a member".
5. Reply: "Wrote `content/code/registrations.py` with
   `fetch_recent(member_id, n=20)`. Smoke test returned 20 rows for
   memberId 123. Per-capability skill
   `code-investigation-registrations` created."
