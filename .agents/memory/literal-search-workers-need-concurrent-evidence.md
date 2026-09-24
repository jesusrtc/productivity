# Literal search workers need concurrent evidence

On the measured multi-core Mac, ripgrep's default worker policy was much slower
for thousands of small files than a smaller pool. Four workers looked best for
one client but took about 323 ms with two overlapping clients. Two workers were
the better measured compromise: single-client median about 138–142 ms versus
220 ms, and two-client median about 202–208 ms versus 382 ms. Concurrent misses
and the single-client first response of 199.93 ms remain important limits.

The retained hint requests two workers only on macOS with more than four
reported CPUs, no nonempty RIPGREP_CONFIG_PATH, and a query containing none of
the regex metacharacters. Keep the query unchanged; do not add fixed-string
mode. Regex, configured tools, small/unknown CPU counts, other platforms and
the Git fallback keep their original arguments. Reevaluate environment and
machine information each request, without caching results or filesystem data.

Do not impose the hint on regexes: the 256 MiB CPU-heavy fixture took about
62 ms with the original policy versus 175 ms with two workers and 338 ms with
one. The complete-output component driver is `lab_code_search_workers.py`;
the real HTTP driver is `lab_code_search_latency.py --repos 1 --search-files 5000`.
Preserve both single and overlapping clients, all first samples, full output
equivalence in the component check, exact response/freshness checks, and cleanup.
Single-client passing results do not establish the overall 200 ms goal.
