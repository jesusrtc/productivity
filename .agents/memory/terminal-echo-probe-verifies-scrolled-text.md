# Terminal latency probes must verify text after the ready marker scrolls away

The normal tmux client viewport can discard the initial ready marker after enough
echoed characters, even when the echo process received and wrote every byte.
Do not cap the run or increase the viewport to hide this boundary.

Use a reproducible varied input stream and track exact visible suffixes after
first verifying the marker. Reject altered/missing text, ambiguous alignment,
insufficient context, output ahead of handled input, and any unseen prefix that
scrolled away. Parse and render observers need separate verified positions so
parsed-only text cannot authorize a render gap. Record actual scrolled reads and
terminal dimensions in the result. Keep measuring from external input through
the cursor-row render, retaining every sample and any failed run.
