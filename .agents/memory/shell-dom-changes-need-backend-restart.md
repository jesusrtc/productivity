# Shell DOM changes need a backend restart

The index template is loaded once when the backend starts. Asset fingerprint
invalidation updates JS/CSS URLs but keeps that original HTML structure, so a
normal browser reload cannot pick up a new shell element. After changing
index.html's DOM, restart the exact running Lab supervisor and verify that GET /
contains the new element before telling the user to reload. Resolve the URL
through scripts/lab-url.sh and check the listener/supervisor identity when more
than one Lab process is running; a state port file can refer to an older process.
