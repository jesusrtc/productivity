# Assistant terminal scope keeps its reserved identity

The auth middleware scopes requests with an Assistant cwd/path to the Assistant
root. Terminal discovery must register that root as `__assistant__` before adding
an unnamed active-root fallback. Otherwise the fallback claims the path under
its directory basename and deduplication drops `__assistant__`, so creating a
session with an explicit cwd fails with “vault '__assistant__' not found”.

Cover both shell and agent session creation, with and without explicit cwd.
Assistant remains an admin-only pseudo-vault outside the real vault registry.
