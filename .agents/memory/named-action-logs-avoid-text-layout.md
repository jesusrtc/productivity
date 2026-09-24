# Named action logs avoid unused rendered-text reads

`error-report.js` describes controls using name, aria-label or title before
falling back to rendered text. Keep the innerText/textContent lookup inside
that fallback. Reading innerText unconditionally can force full-page style
recalculation even though the resulting text is discarded, including on a
Command+K input change while its dialog closes. Preserve attribute precedence,
action/id metadata, and the existing rendered-text fallback for unnamed controls.

The disposable `--quick-files` latency workflow sends timestamped native
Command+K, filter characters, arrows, Enter and Escape. It verifies focused
loaded results, captured root, independent format/time order, complete fixture
files, and the opened document through a paint opportunity. Keep every first
sample; a passing later run does not resolve a prior unexplained cold miss.
