# Focus mode was removed

On 2026-09-15, the user asked to remove Focus mode as unnecessary. Remove
its button, fullscreen handling, layout offsets, and custom pinch zoom.
Do not restore it from the old browser preference. Keep Alive still owns
the browser screen wake lock, while Lid Awake controls the timed macOS
lid-closed behavior. This supersedes the earlier Focus presentation,
navigation, and trackpad-zoom memories.
