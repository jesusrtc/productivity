# Project sidebar ownership includes its children

A `data-project-sidebar` attribute and `_project` state do not prove that a
project directory is still mounted. Normal workspace rendering previously
reused the scope container and replaced its children, causing the project timer
to read `dataset` from null every five seconds. Normal rendering must replace a
project container; project mounting must validate and repair required children.
Pending directory and recent-file callbacks require connected nodes contained
by their captured view, not just a matching scope generation. Keep the real
Chrome replacement/remount/moved-node regression in test_frontend_project_cache.
