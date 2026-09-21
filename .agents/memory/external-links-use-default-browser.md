# External links use the default browser

The user wants external web links to open outside Lab in the system's default
browser, including when Lab runs as an installed Chrome app. Use the shared
`LabExternalLinks` handler for document/sidebar/Assistant links, same-origin
HTML previews, terminal OSC 8 links, and explicit server pop-outs.

Local admin sessions hand HTTP(S) URLs to the authenticated, same-origin
`POST /api/ui/open-external` endpoint (macOS `/usr/bin/open`). Remote sessions
open a new client browser tab; they must never launch the server's desktop.
Internal navigation, downloads, and protocol handlers retain their behavior.
