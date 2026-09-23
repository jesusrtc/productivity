# Search decodes after complete pipe capture

On POSIX, code search collects complete stdout/stderr as bytes with the ordinary
subprocess runner, then strictly decodes stdout followed by stderr. This releases
the runner's intermediate pipe chunks before allocating text. If decoded text
has no carriage return, skip the two universal-newline replacement scans.
For a 27,455,000-byte result, traced Python capture allocations fell from about
82.40 MB to 55.01 MB. Concurrent HTTP median fell from about 182 ms to 139–142 ms;
four of 80 candidate requests still exceeded 200 ms, so the goal remains open.

Select encoding before launching the process with public `io.text_encoding(None)`
and, for its `locale` result, `locale.getencoding()`. This preserves UTF-8 mode
even when the underlying locale is ASCII, and keeps opt-in EncodingWarning.
Do not hardcode UTF-8 or use locale.getencoding alone. Keep full output capture,
both pipe EOFs, strict errors with their complete offending bytes/offsets,
stdout-before-stderr error priority, the original timeout and child reaping.
Invalid output must not bypass process completion or take priority over a timeout.
Non-POSIX uses the original text-mode runner.

Native equivalence tests cover four encodings, mixed/large output, return codes,
both-stream decoding errors, UTF-8/warning flags and delayed descendants. The
HTTP driver retains its complete workload, first samples and fresh-result check.
Worker policy, search arguments, result ordering/parsing and Git fallback are
separate behavior and are unchanged by this capture optimization.
