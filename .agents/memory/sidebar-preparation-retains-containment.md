# Keep containment when preparing sidebar groups

`content-visibility:auto` implicitly provides layout, style and paint containment.
Changing a live group to `visible` during idle preparation removes those boundaries
unless they are retained explicitly. Prepared recent-file groups should therefore
keep `contain:layout style paint`, without size containment. This preserves their
fully laid-out content while bounding paint and hit-test work. A matched 5,000-file
Chrome trace reduced paint time about 47%; it did not prove every key meets budget.

Keep the existing native find, geometry, actions, focus, themes, zoom and resize
checks. The rendering test also compares prepared versus auto group-boundary pixels
with focused history buttons and drop highlights. Separate compositing may round
antialiased corners slightly; use the existing small icon-edge tolerance and retain
pixel statistics, never hide a shifted or clipped control with a broad threshold.
