# Browser page-content extraction can force sidebar layout

Chrome 153.0.8010.53's `AIPageContentAgent::ContentBuilder::Build` was observed in
an isolated, normally configured UI forcing a 138.78 ms layout of a 5,000-file
sidebar during typing. No Lab sidebar replacement ran at that point. The browser
forces activatable display locks, so `content-visibility:auto` alone does not
bound the worst-case cost. Preserve native search and every row; do not disable
browser features merely to obtain a passing timing result.

Use the typing fixture with `LAB_PERF_TRACE=/tmp/input-trace.json`. Its blink and
display-lock trace categories identify this work; a JavaScript CPU profile alone
shows much of it as `(program)`. Use unprofiled runs for final latency numbers.

Also test `--typing --typing-updates`: alternating writes to the fixture's two
documents expose sidebar rebuild delays that unchanged refreshes miss. The probe
verifies actual mtimes in the sidebar cache and the final recent-file order.
