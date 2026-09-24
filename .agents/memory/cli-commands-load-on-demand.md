# Load only the requested CLI command before agent launch

Fresh `lab agents run` processes used to import every root command, including
unrelated Assistant, notebook and HTTP modules. The root Click group now lists
the complete command catalog but imports/caches actual command objects only
when Click resolves them. `agent` and `agents` still resolve to the same object.
Top-level help and completion deliberately load the commands they describe.

Keep command modules, flags, error text, help, shell completion, injected Lab
context, exact conversation arguments and child environment unchanged. Fresh
subprocess regressions cover both agent aliases; an eager-registration control
compares the full recursive command help, version, errors and completion.

Twenty fresh interpreter invocations of `lab agents run --help` measured median
58.93 ms before and 36.09 ms after. This proves reduced launcher overhead, not
that the complete UI meets its budget. Matching untraced document opening was
404.0 versus 383.4 ms cold; the traced candidate was slower at 681.1 ms and must
remain in the evidence. Cold opening still exceeds 200 ms.

Startup diagnostics in the owned Assistant fixture read the existing echo
process record's mtime only during cleanup, and optionally record bounded xterm
parse/render stages. A render callback with matching buffer text is not enough:
require `cursorRendered` before calling it a cursor-row render. Production
launch/admission, terminal rendering, polling and readiness are unchanged.
