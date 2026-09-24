# Separate Lab launch work from provider bootstrap

The owned document-terminal diagnostic now supports `--trace-agent-launch`
with `--assistant-details --server-timings`. It preserves normal interpreter
startup/sitecustomize and delegates through the same runpy module entry, while
recording interpreter-ready and provider-exec-request timestamps. A separate
timestamp immediately before `os.execvpe` is passed only to the owned provider
through a diagnostic environment key, separating trace-file logging overhead.
The provider records its first timestamp before its usual json/pathlib imports.

In the complete 500-note diagnostic, interpreter-ready was at 127.46 ms after
the click and exec was requested at 152.05 ms: 24.60 ms elapsed / 22.66 ms process
CPU for Lab launch work in that interval. Trace logging took 0.17 ms. The actual
handoff marker was at 152.22 ms, but the owned provider's first statement marker
was at 386.26 ms, a 234.04 ms interval. Complete opening took 434.5 ms.

Do not attribute that whole interval to Python imports, rendering, scheduler
delay or a particular OS mechanism without more evidence. It includes process
replacement/interpreter bootstrap and waiting outside the measured Lab module
interval. The provider is a generated owned Python echo CLI, not a real agent;
the diagnostic adds overhead and does not prove physical latency or iTerm parity.
Keep this program, all first-use samples and complete terminal readiness in the
workload. Replacing it with a faster fixture would not establish the UI goal.

The observed boundary shifts the next investigation away from further root-CLI
import changes alone. Default launch behavior and production code are unchanged
by the probe. Reports: `/tmp/lab-agent-process-handoff-full-{browser,server}.json`
and `/tmp/lab-agent-process-summary.json`.
