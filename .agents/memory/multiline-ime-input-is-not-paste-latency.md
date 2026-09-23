# Multiline IME insertion is not clipboard-paste latency

Chrome's CDP `Input.insertText` uses IME insertion. On the measured Chrome 153,
replacing about 101 KB of multiline text generated 9,004 trusted input events
and took 12.6 seconds in a plain textarea without Lab. Flattening the source
while retaining the two revision line breaks took about 10 ms. Do not attribute
the whole multiline control cost to Lab handlers or call it a clipboard-paste
measurement.

The document benchmark keeps full replacement as its default. Its explicit
`--document-edit-input append` mode instead adds a small revision to the same
large document. Preserve both results and label the mode. `inputSetups` reports
external CDP acknowledgement durations, separately from the native click/paint
measurements; failed or >=200 ms setups fail the run. These durations do not
prove the editor has displayed a physical frame. Failed browser workloads must
also stop and save their requested CPU/trace diagnostics before closing Chrome.
