# Objective assets share the shell cache version

Keep workspace-objectives JS/CSS, the Objectives demo wrapper JS/CSS and its
three sandbox files in the index asset fingerprint list. Versioning only the
iframe URL leaves nested scripts/styles cached; serve the sandbox HTML with
that version on all dependency URLs, including the immutable native Markdown
editor. Normal reloads must pick up Objective changes without cache bypass.
The index lifecycle regression changes each asset's mtime independently and
checks shell invalidation plus the seven sandbox dependency URLs.
