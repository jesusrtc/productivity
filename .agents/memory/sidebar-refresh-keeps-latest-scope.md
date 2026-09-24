# Sidebar refreshes belong to one navigation generation

Capture the workspace path and selected file root around sidebar fetches. Check
both scope and a monotonically increasing refresh generation after awaits before
painting or caching; path equality alone misses A → B → A navigation and newer
refreshes of the same workspace. Cached paint and background reconciliation must
reuse their parent's generation. Fetch metadata using the captured path, never
the mutable global workspace after a delayed file read.
