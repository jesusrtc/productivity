# Server pop-outs use the clicking client and saved URL

The embedded server toolbar opens through `LabExternalLinks.open` with
`clientOnly:true`, synchronously within the click. A successful native
`/api/ui/open-external` response can target a different profile and does not
prove that the clicking user got a window.

Restored server tabs can precede the Files sidebar cache. Read the scoped saved
server config before choosing direct/proxy mode and entry path; retain that URL
on the workspace-scoped wrapper for Pop out even if the cache is absent. Guard
late responses against navigation. Never replace a missing entry with `/`.
Regression coverage: `core/tests/test_frontend_server_popout.py`.
