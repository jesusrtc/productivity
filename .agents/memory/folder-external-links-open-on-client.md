# External folder links open on the clicking client

Folder/worktree metadata links use `LabExternalLinks.open(url, {clientOnly:true})`,
matching associated Assistant document links. Loopback requests can come through
SSH forwarding, so `LAB_EXTERNAL_BROWSER` does not prove that the server's desktop
is the user's desktop. A successful `/api/ui/open-external` response can leave the
clicking browser with no visible destination. Keep the browser opening synchronous
within the click and preserve the active-scope guard. Other shared external links
retain their existing OS-browser behavior.
