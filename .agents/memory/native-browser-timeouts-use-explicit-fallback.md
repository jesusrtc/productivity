# Native browser timeouts have an explicit fallback

Chrome's Apple-event window and single-tab queries were observed returning -1712
while native default-browser discovery and version reads worked. Do not assume
that increasing the tab-enumeration deadline fixes this browser state. Fetch tab
URLs in one batch, serialize automation probes, and back off for 30 seconds after
failure. The endpoint returns ok:false plus requires_browser_click and a detail;
the frontend offers a fresh user click without silently opening a duplicate.
Expected unavailable automation is a handled operation result; failure to launch
the ordinary OS opener remains an HTTP error.
