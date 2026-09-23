# Document saves publish confirmed cache content

After a successful workspace-file PUT, update only the content of the captured
document cache entry before refreshing the inline view. Otherwise Save paints
the submitted modal, the stale cached inline document, then the fresh inline
document: three full renders. Keep the normal content/comments/artifact GETs;
changed server data still requires another render.

Capture the workspace, document root, file, source and editor before awaiting
the write. Do not replace a newer cache object or create an incomplete cache
entry. A delayed response must not close or repaint another workspace/root/file,
a reopened editor, or a draft changed during the write. Cache only confirmed
submitted text, and leave failed writes and newer drafts intact.
