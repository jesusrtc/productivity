# Open fresh terminals with visible font metrics

Show the newly owned pane immediately before xterm.open(). In vendored xterm
5.3, opening a display:none pane leaves the initial font/grid measurements
unavailable; fitting immediately afterward then takes the existing 50 ms
_openWS geometry retry. Native traces showed this retry on all six baseline
creations and none after showing the pane first. Keep the valid-dimension
fallback and fit-before-WebSocket rule; do not connect at default geometry.

The change is synchronous and stays after the attach ownership check. Focus,
ResizeObserver cleanup, WebGL enablement and parked-pane policy remain intact.
A Chrome test uses the production fresh-pane fragment and real xterm/FitAddon
at three sizes, verifies fitted dimensions before connection and Unicode/focus,
and reproduces the missing initial geometry on the old source.

Repeated 20-creation medians improved from 221.5/230.4 to 200.7/201.3 ms, with
first-use and other misses retained. This remains a partial latency improvement;
the glyph CPU profile itself did not improve.
